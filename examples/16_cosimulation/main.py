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


def wait_for_invocations(env, expected_count: int, max_wait: float = 10.0, poll_interval: float = 0.1):
    """
    轮询等待 expected_count 个 invocation 完成。

    faas-sim `invocations` 指标按 (function_name, t_start) 累加。
    我们用 `env.metrics.get("invocation")` 拿到的是 counter；这里直接用
    `env.faas` 暴露的 invocation 状态 + env.metrics 提取的 dataframe 行数做检查。

    与 07/08/11/12/14 同样的模式：替代固定 env.timeout(2)，避免 cosim
    高 rps 阶段末尾的 invoke 被截断。
    """
    waited = 0.0
    while waited < max_wait:
        try:
            # faas-sim 的 metric 名是 "invocations"（复数），不是 "invocation"
            df = env.metrics.extract_dataframe("invocations")
            done = len(df)
        except Exception:
            done = 0

        if done >= expected_count:
            return

        yield env.timeout(poll_interval)
        waited += poll_interval

    # max_wait 超时但未达 expected_count：留给 self-check 报警
    logger.warning(
        "wait_for_invocations timeout: expected=%d, done=%d, waited=%.1fs",
        expected_count, done, waited,
    )


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
        # 计算本 benchmark 计划触发的总 request 数（4 phase 求和），
        # 用于 benchmark.run() 末尾 wait_for_invocations(expected_total) 等待所有请求完成
        self.expected_total_requests = sum(
            max(int(phase.rps * phase.duration), 1) for phase in self.external_trace.phases
        )

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

        # 等待所有 phase 触发的 invocation 完成（替代固定 env.timeout(2)，
        # 避免 phase 边界 + 高 rps 场景下尾部 invocation 被截断）
        yield from wait_for_invocations(
            env,
            expected_count=self.expected_total_requests,
            max_wait=10.0,
        )

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
        logger.info("cosim phase invoke summary:\n%s", phase_summary_df.to_string(index=False))

    exchange_summary_df = dfs.get("cosim_exchange_summary")
    if exchange_summary_df is not None and len(exchange_summary_df) > 0:
        logger.info("cosim exchange summary:\n%s", exchange_summary_df.to_string(index=False))

    paper_highlight_df = dfs.get("cosim_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：每 phase 影响倍数
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("impact_relative_to_normal"):
                logger.info("paper highlight: %s = %.3fx", metric, float(value))
            elif metric.startswith("avg_final_duration") or metric.startswith("invoke_events"):
                logger.info("paper highlight: %s = %s", metric, value)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
