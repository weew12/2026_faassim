"""
文件作用：faas-sim 节点级镜像缓存样例。

本样例演示 docker.pull() 与节点本地镜像缓存之间的关系，包括：
- same_node_cache_reuse：同一节点重复部署相同镜像，第二次命中缓存；
- different_node_cold_pull：不同节点首次部署相同镜像，各节点都需要冷拉取；
- 导出 image_cache_probe、flow 和跨场景对比结果。

运行方式：
    python -u examples/13_image_cache/main.py
"""

import logging
import sys
from pathlib import Path
from typing import List, Callable

import pandas as pd

from ether.core import Node, Link, Connection, Capacity
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


def build_minimal_cache_topology() -> Topology:
    """
    构造 image_cache 样例使用的最小拓扑。

    拓扑结构：

    ```text
    DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0
                                          |
                                          -- link_server_1 -- server_1
    ```

    只包含 2 个 server 节点 + 1 个 switch + DockerRegistry，
    方便 SequenceNodeScheduler 在不同场景中可靠地选择 server_0 / server_1。

    **为什么不复用 UrbanSensingScenario**：
    ether.scenarios.urbansensing 在连续两次 `UrbanSensingScenario()` 调用时
    会产生不同的节点集（内部状态污染），导致本样例第二次场景的
    SequenceNodeScheduler.find_node("server_0") 失败、退回到 server_10，
    两个场景的 cache 行为完全一样。
    这里用 ether.core 直接构造最小拓扑，避免这个问题。
    """
    topology = Topology()

    capacity = Capacity(cpu_millis=2000, memory=2 * 1024 * 1024 * 1024)

    server_0 = Node("server_0", capacity=capacity, arch="x86")
    server_1 = Node("server_1", capacity=capacity, arch="x86")

    registry_link = Link(bandwidth=200, tags={"name": "registry_link", "type": "registry_access"})
    link_0 = Link(bandwidth=200, tags={"name": "link_server_0", "type": "node_access"})
    link_1 = Link(bandwidth=200, tags={"name": "link_server_1", "type": "node_access"})

    switch = "switch"
    internet = "internet"

    topology.add_connection(Connection(internet, registry_link, latency=5))
    topology.add_connection(Connection(registry_link, switch, latency=5))

    topology.add_connection(Connection(server_0, link_0, latency=2))
    topology.add_connection(Connection(link_0, switch, latency=1))

    topology.add_connection(Connection(server_1, link_1, latency=2))
    topology.add_connection(Connection(link_1, switch, latency=1))

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
    topology: Topology,
    output_dir: Path,
):
    """
    运行一个镜像缓存场景。

    每个场景使用独立 Simulation，但复用同一份 topology，确保 server_0/server_1
    在不同场景中节点身份一致（避开 ether.scenarios.urbansensing 的状态污染）。
    """
    logger.info("running image cache scenario: %s", scenario_name)

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

    # 复用同一份拓扑：避免连续构造场景带来的状态污染
    topology = build_minimal_cache_topology()

    scenario_summaries = []

    same_node_dfs = run_scenario(
        scenario_name="same_node_cache_reuse",
        scheduler_factory=SequenceNodeScheduler.create_same_node,
        topology=topology,
        output_dir=output_dir,
    )
    scenario_summaries.append(same_node_dfs["image_cache_summary"])

    different_node_dfs = run_scenario(
        scenario_name="different_node_cold_pull",
        scheduler_factory=SequenceNodeScheduler.create_different_node,
        topology=topology,
        output_dir=output_dir,
    )
    scenario_summaries.append(different_node_dfs["image_cache_summary"])

    comparison_result = export_comparison(
        output_dir,
        scenario_summaries,
        same_node_probe_flow_df=same_node_dfs.get("probe_flow_join", pd.DataFrame()),
        different_node_probe_flow_df=different_node_dfs.get("probe_flow_join", pd.DataFrame()),
    )

    comparison_df = comparison_result.get("comparison", pd.DataFrame())
    if comparison_df is not None and len(comparison_df) > 0:
        logger.info("image cache comparison:\n%s", comparison_df.to_string(index=False))

    paper_df = comparison_result.get("paper_highlight", pd.DataFrame())
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    self_check_df = comparison_result.get("self_check", pd.DataFrame())
    if self_check_df is not None and len(self_check_df) > 0:
        passed = int(self_check_df["passed"].sum())
        total = len(self_check_df)
        logger.info("data self-check: %d / %d PASS", passed, total)
        if passed < total:
            for _, row in self_check_df[~self_check_df["passed"]].iterrows():
                logger.warning("  FAILED: %s", row["check_id"])

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
