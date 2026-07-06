"""
文件作用：faas-sim 协同仿真样例。

本样例演示 faas-sim 与外部控制/环境模型之间的最小协同仿真流程：
- 外部 trace 描述不同阶段的负载、运行时间因子和网络延迟；
- ExternalController 按控制周期读取 trace 并更新共享上下文；
- 函数模拟器在 invoke 阶段读取上下文，调整执行时间；
- 输出 cosim_exchange、cosim_phase 和 cosim_invoke_probe 等指标。

运行方式：
    python -u examples/16_cosimulation/main.py
"""

import logging
import sys
from pathlib import Path
from typing import List

import ether.scenarios.urbansensing as scenario
from skippy.core.utils import parse_size_string

from sim import docker
from sim.benchmark import Benchmark
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import (
    FunctionDeployment,
    Function,
    FunctionImage,
    ScalingConfiguration,
    FunctionContainer,
    KubernetesResourceConfiguration,
)
from sim.faassim import Simulation
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from context import CosimulationContext
from controller import ExternalController
from external_model import ExternalEnvironmentTrace
from simulator import CosimulationSimulatorFactory

logger = logging.getLogger(__name__)


def configure_logging():
    """
    配置日志输出。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def example_topology() -> Topology:
    """
    创建 cosimulation 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class CosimulationBenchmark(Benchmark):
    """
    协同仿真实验 Benchmark。

    该 Benchmark 根据外部 trace 的阶段配置逐段触发请求负载。
    ExternalController 同时以固定控制周期运行，形成“外部模型输入 + faas-sim 执行反馈”的最小闭环。
    """

    function_name = "cosim-python-pi"
    image_name = "cosim-python-pi-cpu"

    def __init__(
        self,
        external_trace: ExternalEnvironmentTrace,
        context: CosimulationContext,
        controller: ExternalController,
    ):
        """
        初始化 Benchmark。
        """
        self.external_trace = external_trace
        self.context = context
        self.controller = controller

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("64M"), arch="arm32"))
        containers.put(ImageProperties(self.image_name, parse_size_string("64M"), arch="x86"))
        containers.put(ImageProperties(self.image_name, parse_size_string("64M"), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行协同仿真实验。
        """
        env.process(self.controller.run(env))

        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        for phase in self.external_trace.phases:
            if env.now < phase.start_time:
                yield env.timeout(phase.start_time - env.now)

            self.context.update_from_phase(phase)

            env.metrics.log(
                "cosim_workload_phase",
                {
                    "start_time": phase.start_time,
                    "duration": phase.duration,
                    "rps": phase.rps,
                    "runtime_factor": phase.runtime_factor,
                    "network_delay": phase.network_delay,
                    "max_requests": int(phase.rps * phase.duration),
                },
                phase_name=phase.phase_name,
                controller_action=phase.controller_action,
                description=phase.description,
            )

            logger.info(
                "[simtime=%.2f] start workload phase=%s rps=%.2f duration=%.2f",
                env.now,
                phase.phase_name,
                phase.rps,
                phase.duration,
            )

            ia_generator = static_arrival_profile(
                constant_rps_profile(rps=phase.rps)
            )

            yield from function_trigger(
                env,
                deployments[0],
                ia_generator,
                max_requests=max(int(phase.rps * phase.duration), 1),
            )

        yield env.timeout(2)

        logger.info("cosimulation workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_cosim_deployment()]

    def prepare_cosim_deployment(self) -> FunctionDeployment:
        """
        准备协同仿真函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="150m",
            memory="128Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 2
        scaling_config.scale_max = 2

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    cosimulation 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    trace_path = root_dir / "inputs" / "external_environment_trace.csv"

    logger.info("using external trace: %s", trace_path)

    context = CosimulationContext()
    external_trace = ExternalEnvironmentTrace(trace_path)
    controller = ExternalController(
        external_trace=external_trace,
        context=context,
        control_interval=0.5,
    )

    logger.info("creating cosimulation topology")
    topology = example_topology()

    logger.info("creating cosimulation benchmark")
    benchmark = CosimulationBenchmark(
        external_trace=external_trace,
        context=context,
        controller=controller,
    )

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark, name="cosimulation")

    sim.create_simulator_factory = lambda: CosimulationSimulatorFactory(context)

    logger.info("running simulation")
    sim.run()

    output_dir = root_dir / "outputs"
    dfs = export_outputs(sim, output_dir, external_trace)

    phase_summary_df = dfs.get("cosim_phase_invoke_summary")
    if phase_summary_df is not None and len(phase_summary_df) > 0:
        logger.info("cosim phase invoke summary:\\n%s", phase_summary_df.to_string(index=False))

    exchange_summary_df = dfs.get("cosim_exchange_summary")
    if exchange_summary_df is not None and len(exchange_summary_df) > 0:
        logger.info("cosim exchange summary:\\n%s", exchange_summary_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
