"""
文件作用：faas-sim 性能退化样例。

本样例演示同一节点存在多个并发请求时，函数执行时间随节点竞争程度增加而变长的建模方法，包括：
- 固定调度到同一节点；
- 部署多个函数副本；
- 使用高并发请求制造资源竞争；
- 根据 node.current_requests 计算退化后的执行时间；
- 导出 degradation_probe 和调用结果指标。

运行方式：
    python -u examples/08_degradation/main.py
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
from scheduler import FixedNodeScheduler
from simulator import DegradationSimulatorFactory

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
    创建 degradation 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class DegradationBenchmark(Benchmark):
    """
    性能退化实验 Benchmark。

    该 Benchmark 部署一个拥有 3 个副本的函数，并通过较高请求速率制造并发。
    固定节点调度器会将副本放置到同一节点，从而稳定触发共节点并发退化。
    """

    function_name = "degradation-python-pi"
    image_name = "degradation-python-pi-cpu"

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
        运行性能退化实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        logger.info("triggering degradation workload")

        # 较高请求速率用于制造请求重叠，从而触发 active_requests_before > 0。
        ia_generator = static_arrival_profile(constant_rps_profile(rps=18))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=40,
        )

        # 等待尾部请求完成，确保资源释放和调用指标完整。
        yield env.timeout(3)

        logger.info("degradation workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_degradation_deployment()]

    def prepare_degradation_deployment(self) -> FunctionDeployment:
        """
        准备性能退化函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="150m",
            memory="128Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 3
        scaling_config.scale_max = 3

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    degradation 样例入口。
    """
    configure_logging()

    logger.info("creating degradation topology")
    topology = example_topology()

    logger.info("creating degradation benchmark")
    benchmark = DegradationBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 固定调度到同一节点，稳定制造共节点并发场景。
    sim.create_scheduler = FixedNodeScheduler.create

    # 使用带性能退化模型的函数模拟器。
    sim.create_simulator_factory = DegradationSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    degradation_summary_df = dfs.get("degradation_summary")
    if degradation_summary_df is not None and len(degradation_summary_df) > 0:
        logger.info("degradation summary:\\n%s", degradation_summary_df.to_string(index=False))

    concurrency_distribution_df = dfs.get("degradation_concurrency_distribution")
    if concurrency_distribution_df is not None and len(concurrency_distribution_df) > 0:
        logger.info("degradation concurrency distribution:\\n%s", concurrency_distribution_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
