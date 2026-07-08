"""
文件作用：faas-sim 原生 ResourceMonitor 资源监控样例。

本样例演示如何通过 ResourceState 和 ResourceMonitor 观察函数执行期间的资源使用变化，包括：
- 函数 invoke 阶段显式登记 CPU / memory；
- 函数执行结束后释放资源；
- ResourceMonitor 周期性采集资源状态；
- 导出资源监控和调用结果指标；
- 论文 demo 关键摘要 + 数据自检。

运行方式：
    python -u examples/06_resource_monitor/main.py
    python -u examples/06_resource_monitor/plot.py
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
    FunctionState,
)
from sim.faassim import Simulation
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from simulator import ResourceMonitorSimulatorFactory

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


# 全局复用：避免 ether.scenarios.urbansensing 状态污染（与 02/03/05 一致风格）。
# 原版用 UrbanSensingScenario，Skippy 默认 MostLoaded 把 2 replica 全堆 server_0，
# 改造后仍能复现"双 replica 都在 server_0"的核心 demo（资源监控关键）。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建 ResourceMonitor 样例使用的最小 4-server 拓扑。

    端到端瓶颈：节点 cpu/mem 容量，由 simulator.py 显式 put_resource 触发。

    返回：每次调用都返回同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        cap = Capacity(cpu_millis=4000, memory=2 * 1024 * 1024 * 1024)

        registry_link = Link(bandwidth=200, tags={"name": "registry_link", "type": "registry_access"})
        topology.add_connection(Connection("internet", registry_link, latency=5))
        topology.add_connection(Connection(registry_link, "switch", latency=5))

        for i in range(4):
            node = Node(f"server_{i}", capacity=cap, arch="x86")
            link = Link(bandwidth=200, tags={"name": f"link_server_{i}", "type": "node_access"})
            topology.add_connection(Connection(node, link, latency=2))
            topology.add_connection(Connection(link, "switch", latency=1))

        topology.init_docker_registry()
        _SHARED_TOPOLOGY = topology

    return _SHARED_TOPOLOGY


class ResourceMonitorBenchmark(Benchmark):
    """
    资源监控实验 Benchmark。

    该 Benchmark 部署一个函数 resource-heavy-python-pi，
    保持两个副本，并触发一批请求。函数执行期间会显式登记 CPU / memory，
    以便 ResourceMonitor 采集资源变化。
    """

    function_name = "resource-heavy-python-pi"
    image_name = "resource-heavy-python-pi-cpu"

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
        运行资源监控实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replicas")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))
        while len(env.faas.get_replicas(deployments[0].name, FunctionState.RUNNING)) < 2:
            yield env.timeout(0.1)

        logger.info("triggering resource monitor workload")

        ia_generator = static_arrival_profile(constant_rps_profile(rps=3))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=12,
        )

        # 额外等待一段时间，使 ResourceMonitor 有机会采集到资源释放后的状态。
        yield env.timeout(3)

        logger.info("resource monitor workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_resource_heavy_deployment()]

    def prepare_resource_heavy_deployment(self) -> FunctionDeployment:
        """
        准备资源密集函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="300m",
            memory="256Mi",
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
    resource_monitor 样例入口。
    """
    configure_logging()

    logger.info("creating resource monitor topology")
    topology = example_topology()

    logger.info("creating resource monitor benchmark")
    benchmark = ResourceMonitorBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 使用显式登记 CPU / memory 的函数模拟器。
    sim.create_simulator_factory = ResourceMonitorSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    resource_summary_df = dfs.get("resource_monitor_summary")
    if resource_summary_df is not None and len(resource_summary_df) > 0:
        logger.info("resource monitor summary:\n%s", resource_summary_df.to_string(index=False))

    per_replica_df = dfs.get("resource_utilization_per_replica")
    if per_replica_df is not None and len(per_replica_df) > 0:
        logger.info("resource utilization per replica:\n%s", per_replica_df.to_string(index=False))

    join_df = dfs.get("invocation_resource_join")
    if join_df is not None and len(join_df) > 0:
        logger.info(
            "invocation × resource join (first 6 rows):\n%s",
            join_df.head(6).to_string(index=False),
        )

    invocation_summary_df = dfs.get("resource_monitor_invocation_summary")
    if invocation_summary_df is not None and len(invocation_summary_df) > 0:
        logger.info("resource monitor invocation summary:\n%s", invocation_summary_df.to_string(index=False))

    paper_df = dfs.get("resource_monitor_paper_highlight")
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    self_check_df = dfs.get("resource_monitor_self_check")
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
