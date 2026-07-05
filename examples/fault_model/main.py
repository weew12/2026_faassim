"""
文件作用：faas-sim 故障模型样例。

本样例演示如何在函数执行模拟器中引入故障模型，包括：
- 节点不可用窗口；
- 周期性函数副本错误；
- 网络退化导致的执行时间增加；
- 故障事件时间线和请求结果导出。

运行方式：
    python -u examples/fault_model/main.py
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
from fault_model import DeterministicFaultModel
from scheduler import FixedNodeScheduler
from simulator import FaultModelSimulatorFactory

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
    创建 fault_model 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class FaultModelBenchmark(Benchmark):
    """
    故障模型实验 Benchmark。

    该 Benchmark 部署一个拥有两个副本的函数，并触发一批请求。
    函数副本固定部署到 server_0，便于故障模型稳定作用于目标节点。
    """

    function_name = "fault-prone-python-pi"
    image_name = "fault-prone-python-pi-cpu"

    def __init__(self, fault_model: DeterministicFaultModel):
        """
        初始化 Benchmark。
        """
        self.fault_model = fault_model

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
        运行故障模型实验。
        """
        # 启动故障时间线记录协程。
        env.process(self.fault_model.emit_timeline(env))

        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        logger.info("triggering fault model workload")

        ia_generator = static_arrival_profile(constant_rps_profile(rps=6))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=30,
        )

        # 等待尾部请求和故障时间线写入完成。
        yield env.timeout(4)

        logger.info("fault model workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_fault_prone_deployment()]

    def prepare_fault_prone_deployment(self) -> FunctionDeployment:
        """
        准备故障模型函数部署对象。
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
    fault_model 样例入口。
    """
    configure_logging()

    fault_model = DeterministicFaultModel()

    logger.info("creating fault model topology")
    topology = example_topology()

    logger.info("creating fault model benchmark")
    benchmark = FaultModelBenchmark(fault_model)

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 固定部署到目标节点，使节点故障窗口稳定影响函数请求。
    sim.create_scheduler = FixedNodeScheduler.create

    # 使用带故障判定逻辑的函数模拟器。
    sim.create_simulator_factory = lambda: FaultModelSimulatorFactory(fault_model)

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir, fault_model)

    fault_summary_df = dfs.get("fault_model_summary")
    if fault_summary_df is not None and len(fault_summary_df) > 0:
        logger.info("fault model summary:\\n%s", fault_summary_df.to_string(index=False))

    fault_reason_df = dfs.get("fault_reason_distribution")
    if fault_reason_df is not None and len(fault_reason_df) > 0:
        logger.info("fault reason distribution:\\n%s", fault_reason_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
