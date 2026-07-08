"""
文件作用：faas-sim 镜像拉取网络样例。

本样例演示 docker.pull() 与网络 Flow 的关系，包括：
- 第一次部署小镜像时触发 docker_pull 网络流；
- 同一节点第二次部署同一镜像时复用节点镜像缓存；
- 部署大镜像时产生更长镜像拉取耗时；
- 导出 image_pull_probe、flow、invoke 探针和部署生命周期指标；
- 论文 demo 关键摘要 + 数据自检。

运行方式：
    python -u examples/05_image_pull_network/main.py
    python -u examples/05_image_pull_network/plot.py
"""

import logging
import sys
from pathlib import Path
from typing import List

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
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from scheduler import FixedNodeScheduler
from simulator import ImagePullSimulatorFactory

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


# 全局复用：避免 ether.scenarios.urbansensing 状态污染（与 02/03 一致风格）。
# 原版用 UrbanSensingScenario 但 FixedNodeScheduler 强制选 server_0，所以拓扑污染对结果影响有限。
# 不过为了与其他样例保持统一，改用最小 4-server + DockerRegistry 拓扑。
# registry_link / server link 用 1000Mbps：保留原版 pull_speed ≈ 121 MB/s 的论文数字。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建镜像拉取网络样例使用的最小 4-server 拓扑。

    链路设计：
    - internet -- registry_link(1000Mbps) -- switch
    - switch -- link_server_X(1000Mbps) -- server_X (X=0..3)

    端到端瓶颈：1000Mbps（保留原版 cloudlet 1Gbps 的 pull_speed 数字）。
    small=32M 拉取 ~0.27s, large=192M 拉取 ~1.59s。

    返回：每次调用都返回同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        cap = Capacity(cpu_millis=4000, memory=2 * 1024 * 1024 * 1024)

        registry_link = Link(bandwidth=1000, tags={"name": "registry_link", "type": "registry_access"})
        topology.add_connection(Connection("internet", registry_link, latency=5))
        topology.add_connection(Connection(registry_link, "switch", latency=5))

        for i in range(4):
            node = Node(f"server_{i}", capacity=cap, arch="x86")
            link = Link(bandwidth=1000, tags={"name": f"link_server_{i}", "type": "node_access"})
            topology.add_connection(Connection(node, link, latency=2))
            topology.add_connection(Connection(link, "switch", latency=1))

        topology.init_docker_registry()
        _SHARED_TOPOLOGY = topology

    return _SHARED_TOPOLOGY


class ImagePullNetworkBenchmark(Benchmark):
    """
    镜像拉取网络实验 Benchmark。

    该 Benchmark 依次部署三个函数：
    - image-pull-small-cold：首次部署 small 镜像，应触发网络拉取；
    - image-pull-small-warm：复用相同 small 镜像，且固定调度到同一节点，应命中镜像缓存；
    - image-pull-large-cold：首次部署 large 镜像，应触发更大的网络拉取。
    """

    small_image_name = "image-pull-small-cpu"
    large_image_name = "image-pull-large-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。

        为三种架构注册同名镜像，避免架构不匹配导致调度失败。
        """
        containers: docker.ContainerRegistry = env.container_registry

        for image_name, size in [
            (self.small_image_name, "32M"),
            (self.large_image_name, "192M"),
        ]:
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="arm32"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="x86"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行镜像拉取网络实验。

        通过顺序部署函数，稳定观察冷拉取与缓存复用。
        在第三个函数部署完成后，触发少量小镜像请求，
        让 invocations.csv 也有数据，使样例输出文件清单完整。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            logger.info("deploying %s", deployment.name)
            yield from env.faas.deploy(deployment)

            logger.info("waiting for replica of %s", deployment.name)
            yield env.process(env.faas.poll_available_replica(deployment.name))

            # 增加一个很短的间隔，使不同部署阶段在日志和指标中更容易区分。
            yield env.timeout(0.2)

        # 给 small-cold 触发少量请求，让 invocations.csv 有数据。
        # 选 small-cold 是因为它的镜像已经在 server_0 缓存，请求路径最快。
        # 选 10 个请求 + 10 RPS 是为了演示完整调用链而不拖慢仿真。
        logger.info("triggering demo workload on small-cold")
        small_ia = static_arrival_profile(constant_rps_profile(rps=10))
        yield from function_trigger(
            env,
            deployments[0],
            small_ia,
            max_requests=10,
        )

        # 等所有 invoke 完成。function_trigger 不等 invoke 进程完成。
        # 05 的 invoke 耗时 0.05s，10 个请求在 1s 内全部分发完，留 1s 缓冲足够。
        yield env.timeout(1.0)

        logger.info("image pull network benchmark finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [
            self.prepare_deployment("image-pull-small-cold", self.small_image_name),
            self.prepare_deployment("image-pull-small-warm", self.small_image_name),
            self.prepare_deployment("image-pull-large-cold", self.large_image_name),
        ]

    def prepare_deployment(self, function_name: str, image_name: str) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        fn_image = FunctionImage(image=image_name)
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


def main():
    """
    镜像拉取网络样例入口。
    """
    configure_logging()

    logger.info("creating image pull network topology")
    topology = example_topology()

    logger.info("creating image pull network benchmark")
    benchmark = ImagePullNetworkBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 固定调度到同一节点，便于观察第二次部署同一镜像时的缓存复用。
    sim.create_scheduler = FixedNodeScheduler.create

    # 使用带镜像拉取探针的函数模拟器。
    sim.create_simulator_factory = ImagePullSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    image_pull_summary_df = dfs.get("image_pull_summary")
    if image_pull_summary_df is not None and len(image_pull_summary_df) > 0:
        logger.info("image pull summary:\n%s", image_pull_summary_df.to_string(index=False))

    flow_summary_df = dfs.get("image_pull_flow_summary")
    if flow_summary_df is not None and len(flow_summary_df) > 0:
        logger.info("image pull flow summary:\n%s", flow_summary_df.to_string(index=False))

    cold_warm_df = dfs.get("image_pull_cold_warm_comparison")
    if cold_warm_df is not None and len(cold_warm_df) > 0:
        logger.info("image pull cold/warm comparison:\n%s", cold_warm_df.to_string(index=False))

    size_duration_df = dfs.get("image_pull_size_duration_comparison")
    if size_duration_df is not None and len(size_duration_df) > 0:
        logger.info("image pull size vs duration:\n%s", size_duration_df.to_string(index=False))

    paper_df = dfs.get("image_pull_paper_highlight")
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    self_check_df = dfs.get("image_pull_self_check")
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
