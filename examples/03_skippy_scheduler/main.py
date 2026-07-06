"""
文件作用：faas-sim 原生 Skippy 默认调度机制样例。

本样例演示如何观察 Skippy 默认调度过程，包括：
- 资源过滤；
- 节点可行性判断；
- 默认优先级打分后的节点选择；
- SchedulingResult 中 suggested_host / feasible_nodes / needed_images 的含义；
- 调度指标导出。

运行方式：
    python -u examples/03_skippy_scheduler/main.py
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
from scheduler import InstrumentedSkippyScheduler
from simulator import SkippySchedulerSimulatorFactory

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
    创建 Skippy 调度样例使用的拓扑。

    当前复用 UrbanSensingScenario，保持与官方样例风格一致。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class SkippySchedulerBenchmark(Benchmark):
    """
    Skippy 调度实验 Benchmark。

    该 Benchmark 部署两个函数：
    - skippy-small：资源请求较小；
    - skippy-medium：资源请求较大。

    通过不同资源请求，可以观察 Skippy 资源过滤和节点选择结果。
    """

    small_fn_name = "skippy-small"
    small_image_name = "skippy-small-cpu"

    medium_fn_name = "skippy-medium"
    medium_image_name = "skippy-medium-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。

        为 arm32、x86、aarch64 三种架构注册镜像，避免因为镜像架构缺失导致调度失败。
        """
        containers: docker.ContainerRegistry = env.container_registry

        for image_name, size in [
            (self.small_image_name, "32M"),
            (self.medium_image_name, "96M"),
        ]:
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="arm32"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="x86"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行 Skippy 调度实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replicas")
        for deployment in deployments:
            yield env.process(env.faas.poll_available_replica(deployment.name))

        logger.info("triggering skippy scheduler workload")

        small_ia = static_arrival_profile(constant_rps_profile(rps=10))
        medium_ia = static_arrival_profile(constant_rps_profile(rps=6))

        yield from function_trigger(
            env,
            deployments[0],
            small_ia,
            max_requests=20,
        )

        yield from function_trigger(
            env,
            deployments[1],
            medium_ia,
            max_requests=12,
        )

        logger.info("skippy scheduler workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [
            self.prepare_small_deployment(),
            self.prepare_medium_deployment(),
        ]

    def prepare_small_deployment(self) -> FunctionDeployment:
        """
        准备小资源函数部署对象。
        """
        return self._prepare_deployment(
            function_name=self.small_fn_name,
            image_name=self.small_image_name,
            cpu="50m",
            memory="64Mi",
            scale_min=2,
            scale_max=2,
        )

    def prepare_medium_deployment(self) -> FunctionDeployment:
        """
        准备中等资源函数部署对象。
        """
        return self._prepare_deployment(
            function_name=self.medium_fn_name,
            image_name=self.medium_image_name,
            cpu="250m",
            memory="256Mi",
            scale_min=2,
            scale_max=2,
        )

    def _prepare_deployment(
        self,
        function_name: str,
        image_name: str,
        cpu: str,
        memory: str,
        scale_min: int,
        scale_max: int,
    ) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        fn_image = FunctionImage(image=image_name)
        fn = Function(function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu=cpu,
            memory=memory,
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = scale_min
        scaling_config.scale_max = scale_max

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    Skippy 调度样例入口。
    """
    configure_logging()

    logger.info("creating skippy scheduler topology")
    topology = example_topology()

    logger.info("creating skippy scheduler benchmark")
    benchmark = SkippySchedulerBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 使用可观测 Skippy 调度器。调度语义仍是 Skippy 默认过滤与打分逻辑。
    sim.create_scheduler = InstrumentedSkippyScheduler.create

    # 使用稳定执行时间模拟器，便于聚焦调度结果。
    sim.create_simulator_factory = SkippySchedulerSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    summary_df = dfs.get("skippy_scheduler_summary")
    if summary_df is not None:
        logger.info("skippy scheduler summary:\\n%s", summary_df.to_string(index=False))

    selected_node_df = dfs.get("skippy_selected_node_distribution")
    if selected_node_df is not None and len(selected_node_df) > 0:
        logger.info("skippy selected node distribution:\\n%s", selected_node_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
