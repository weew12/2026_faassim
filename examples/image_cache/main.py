"""
文件作用：faas-sim 节点级镜像缓存样例。

本样例演示 docker.pull() 与节点本地镜像缓存之间的关系，包括：
- same_node_cache_reuse：同一节点重复部署相同镜像，第二次命中缓存；
- different_node_cold_pull：不同节点首次部署相同镜像，各节点都需要冷拉取；
- 导出 image_cache_probe、flow 和跨场景对比结果。

运行方式：
    python -u examples/image_cache/main.py
"""

import logging
import sys
from pathlib import Path
from typing import List, Callable

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
from sim.topology import Topology

from analysis import (
    export_scenario_outputs,
    export_comparison,
)
from scheduler import SequenceNodeScheduler
from simulator import ImageCacheSimulatorFactory

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
    创建 image_cache 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class ImageCacheBenchmark(Benchmark):
    """
    镜像缓存实验 Benchmark。

    该 Benchmark 顺序部署两个函数，这两个函数使用同一个镜像。
    不同场景通过调度器控制两个副本是否落到同一节点。
    """

    image_name = "image-cache-shared-cpu"

    def __init__(self, scenario_name: str):
        """
        初始化 Benchmark。
        """
        self.scenario_name = scenario_name

    def setup(self, env: Environment):
        """
        注册共享镜像。

        为三种架构注册同名镜像，避免因为目标节点架构不同导致镜像缺失。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("128M"), arch="arm32"))
        containers.put(ImageProperties(self.image_name, parse_size_string("128M"), arch="x86"))
        containers.put(ImageProperties(self.image_name, parse_size_string("128M"), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行镜像缓存实验。

        顺序部署两个函数，保证第二个函数部署时可以观察第一个函数是否留下了节点镜像缓存。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            logger.info("deploying function=%s scenario=%s", deployment.name, self.scenario_name)
            yield from env.faas.deploy(deployment)

            logger.info("waiting for replica of %s", deployment.name)
            yield env.process(env.faas.poll_available_replica(deployment.name))

            # 留出一点仿真时间，使日志和指标更容易区分。
            yield env.timeout(0.2)

        logger.info("image cache benchmark finished scenario=%s", self.scenario_name)

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造两个使用同一镜像的函数部署。
        """
        return [
            self.prepare_deployment("image-cache-first"),
            self.prepare_deployment("image-cache-second"),
        ]

    def prepare_deployment(self, function_name: str) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="100m",
            memory="128Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 1
        scaling_config.scale_max = 1

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def run_scenario(
    scenario_name: str,
    scheduler_factory: Callable[[Environment], object],
    output_dir: Path,
):
    """
    运行一个镜像缓存场景。

    每个场景使用独立 Simulation，避免不同场景之间的节点镜像缓存互相污染。
    """
    logger.info("running image cache scenario: %s", scenario_name)

    topology = example_topology()
    benchmark = ImageCacheBenchmark(scenario_name)

    sim = Simulation(topology, benchmark, name=scenario_name)

    sim.create_scheduler = scheduler_factory
    sim.create_simulator_factory = lambda: ImageCacheSimulatorFactory(scenario_name)

    sim.run()

    dfs = export_scenario_outputs(sim, scenario_name, output_dir)
    return dfs


def main():
    """
    image_cache 样例入口。
    """
    configure_logging()

    output_dir = Path(__file__).resolve().parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_summaries = []

    same_node_dfs = run_scenario(
        scenario_name="same_node_cache_reuse",
        scheduler_factory=SequenceNodeScheduler.create_same_node,
        output_dir=output_dir,
    )
    scenario_summaries.append(same_node_dfs["image_cache_summary"])

    different_node_dfs = run_scenario(
        scenario_name="different_node_cold_pull",
        scheduler_factory=SequenceNodeScheduler.create_different_node,
        output_dir=output_dir,
    )
    scenario_summaries.append(different_node_dfs["image_cache_summary"])

    comparison_df = export_comparison(output_dir, scenario_summaries)

    if comparison_df is not None and len(comparison_df) > 0:
        logger.info("image cache comparison:\\n%s", comparison_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
