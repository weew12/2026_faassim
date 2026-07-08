"""
文件作用：faas-sim 原生 Skippy 默认调度机制样例。

本样例演示如何观察 Skippy 默认调度过程，包括：
- 资源过滤；
- 节点可行性判断；
- 默认优先级打分后的节点选择；
- SchedulingResult 中 suggested_host / feasible_nodes / needed_images 的含义；
- 调度指标导出与论文 demo 关键摘要。

运行方式：
    python -u examples/03_skippy_scheduler/main.py
    python -u examples/03_skippy_scheduler/plot.py
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


# 全局复用：避免 ether.scenarios.urbansensing 状态污染。
# 历史问题：原先复用 UrbanSensingScenario 会让 41 个 candidate node 在 Pod 调度时
# 全堆在 server_0（MostLoadedPriority 默认行为 + UrbanSensingScenario 节点命名不规范），
# 导致 03 demo 的 selected_node_distribution 只剩 1 行，看不到调度多样性。
# 这里改用最小 4-server 拓扑（与 02_load_balancer 风格一致）。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建 Skippy 调度样例使用的最小 4-server 拓扑。

    4 个 server 资源故意做成异构：
    - server_0：大节点；
    - server_1/server_2：中等节点；
    - server_3：小节点。

    这样 small / medium / large 三类函数会产生不同可行节点集合，便于观察
    Skippy 的资源谓词过滤效果。

    返回：每次调用都返回同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        # 镜像拉取链路：DockerRegistry -- internet_link -- switch -- link_server_X -- server_X
        registry_link = Link(bandwidth=200, tags={"name": "registry_link", "type": "registry_access"})
        topology.add_connection(Connection("internet", registry_link, latency=5))
        topology.add_connection(Connection(registry_link, "switch", latency=5))

        node_specs = [
            ("server_0", 4000, 2 * 1024 * 1024 * 1024),
            ("server_1", 1600, 1024 * 1024 * 1024),
            ("server_2", 1600, 1024 * 1024 * 1024),
            ("server_3", 600, 512 * 1024 * 1024),
        ]

        for i, (name, cpu_millis, memory) in enumerate(node_specs):
            cap = Capacity(cpu_millis=cpu_millis, memory=memory)
            node = Node(name, capacity=cap, arch="x86")
            link = Link(bandwidth=200, tags={"name": f"link_server_{i}", "type": "node_access"})
            topology.add_connection(Connection(node, link, latency=2))
            topology.add_connection(Connection(link, "switch", latency=1))

        topology.init_docker_registry()
        _SHARED_TOPOLOGY = topology

    return _SHARED_TOPOLOGY


class SkippySchedulerBenchmark(Benchmark):
    """
    Skippy 调度实验 Benchmark。

    该 Benchmark 部署三个函数：
    - skippy-small：资源请求较小；
    - skippy-medium：资源请求中等；
    - skippy-large：资源请求较大。

    通过不同资源请求，可以观察 Skippy 资源过滤、节点选择和镜像缓存复用结果。
    """

    small_fn_name = "skippy-small"
    small_image_name = "skippy-small-cpu"

    medium_fn_name = "skippy-medium"
    medium_image_name = "skippy-medium-cpu"

    large_fn_name = "skippy-large"
    large_image_name = "skippy-large-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。

        为 arm32、x86、aarch64 三种架构注册镜像，避免因为镜像架构缺失导致调度失败。
        """
        containers: docker.ContainerRegistry = env.container_registry

        for image_name, size in [
            (self.small_image_name, "32M"),
            (self.medium_image_name, "96M"),
            (self.large_image_name, "128M"),
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
        deployments_by_name = {deployment.name: deployment for deployment in deployments}

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replicas")
        for deployment in deployments:
            yield env.process(env.faas.poll_available_replica(deployment.name))

        logger.info("triggering skippy scheduler workload")

        small_ia = static_arrival_profile(constant_rps_profile(rps=10))
        medium_ia = static_arrival_profile(constant_rps_profile(rps=6))
        large_ia = static_arrival_profile(constant_rps_profile(rps=4))

        yield from function_trigger(
            env,
            deployments_by_name[self.small_fn_name],
            small_ia,
            max_requests=20,
        )

        yield from function_trigger(
            env,
            deployments_by_name[self.medium_fn_name],
            medium_ia,
            max_requests=12,
        )

        yield from function_trigger(
            env,
            deployments_by_name[self.large_fn_name],
            large_ia,
            max_requests=8,
        )

        # 等所有 invoke 进程完成。
        # function_trigger(max_requests=N) 只保证触发 N 个请求就返回，
        # 不等待 N 次 invoke 全部跑完。在本样例中每个 invoke 耗时 0.25s，
        # 留 2s 缓冲即可让 20+12+8=40 个请求全部完成并写入 invocations.csv，
        # 使调度结果与 invocation 记录一致，summary 数据自洽。
        yield env.timeout(2.0)

        logger.info("skippy scheduler workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [
            self.prepare_large_deployment(),
            self.prepare_medium_deployment(),
            self.prepare_small_deployment(),
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
            cpu="900m",
            memory="768Mi",
            scale_min=2,
            scale_max=2,
        )

    def prepare_large_deployment(self) -> FunctionDeployment:
        """
        准备大资源函数部署对象。
        """
        return self._prepare_deployment(
            function_name=self.large_fn_name,
            image_name=self.large_image_name,
            cpu="1700m",
            memory="1536Mi",
            scale_min=1,
            scale_max=1,
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
        logger.info("skippy scheduler summary:\n%s", summary_df.to_string(index=False))

    selected_node_df = dfs.get("skippy_selected_node_distribution")
    if selected_node_df is not None and len(selected_node_df) > 0:
        logger.info("skippy selected node distribution:\n%s", selected_node_df.to_string(index=False))

    feasible_df = dfs.get("skippy_feasible_nodes_per_pod")
    if feasible_df is not None and len(feasible_df) > 0:
        logger.info("feasible nodes per pod:\n%s", feasible_df.to_string(index=False))

    node_stats_df = dfs.get("skippy_node_scheduling_stats")
    if node_stats_df is not None and len(node_stats_df) > 0:
        logger.info("node scheduling stats:\n%s", node_stats_df.to_string(index=False))

    paper_df = dfs.get("skippy_paper_highlight")
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    join_df = dfs.get("skippy_schedule_probe_invocation_join")
    if join_df is not None and len(join_df) > 0:
        logger.info("schedule probe × invocation join:\n%s", join_df.to_string(index=False))

    self_check_df = dfs.get("skippy_self_check")
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
