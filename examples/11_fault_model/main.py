"""
文件作用：faas-sim 故障模型样例。

本样例演示如何在函数执行模拟器中引入故障模型，包括：
- 节点不可用窗口；
- 周期性函数副本错误；
- 网络退化导致的执行时间增加；
- 故障事件时间线和请求结果导出。

运行方式：
    python -u examples/11_fault_model/main.py
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


# 全局复用：避免 ether.scenarios.urbansensing 的内部状态污染
# 11 之前直接用 UrbanSensingScenario；为了和 02-10 统一，改用最小 4-server 拓扑
# 构造一次复用。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建 fault_model 样例使用的最小 4-server 拓扑。

    为什么不复用 UrbanSensingScenario：
    ether.scenarios.urbansensing 在连续构造时会返回不同的节点集
    （server_0..9、server_10..19、...、server_70..79），可能让固定节点调度
    选不到预期节点。这里用 ether.core 直接构造 4 个 server 节点 + Docker
    Registry，构造一次复用。

    返回：每次调用都返回同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        cap = Capacity(cpu_millis=4000, memory=2 * 1024 * 1024 * 1024)

        # 镜像拉取链路：DockerRegistry -- internet_link -- switch -- link_server_X -- server_X
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


def wait_for_invocations(env, expected_count: int, max_wait: float = 30.0, poll_interval: float = 0.1):
    """
    轮询 env.metrics.records 直到 invocations 记录数达到 expected_count，
    或等到 max_wait simtime 秒后退出（避免死等）。

    faas-sim 的 function_trigger(max_requests=N) 只保证 N 个请求被触发（queued），
    不等待 N 次 invoke 全部跑完。原来的实现用 `env.timeout(4)` 硬等待，
    当故障模型放大执行时间时容易丢请求；这里改成"看到 N 条 invocations 记录"。

    返回：实际等待的 simtime 秒数。
    """
    start = env.now
    while env.now - start < max_wait:
        count = sum(
            1 for r in env.metrics.records if r.measurement == "invocations"
        )
        if count >= expected_count:
            return env.now - start
        yield env.timeout(poll_interval)
    return env.now - start


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
        # 原来用 env.timeout(4) 硬等待，但故障模型放大执行时间时可能不够。
        # 这里轮询 env.metrics.records 直到 invocations 数达到 30，或最多等 30 simtime 秒。
        expected_total = 30
        waited = yield from wait_for_invocations(env, expected_total, max_wait=30.0)
        logger.info(
            "waited %.2f simtime seconds for %d invocations to finish",
            waited, expected_total,
        )

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
        logger.info("fault model summary:\n%s", fault_summary_df.to_string(index=False))

    fault_reason_df = dfs.get("fault_reason_distribution")
    if fault_reason_df is not None and len(fault_reason_df) > 0:
        logger.info("fault reason distribution:\n%s", fault_reason_df.to_string(index=False))

    window_check_df = dfs.get("probe_fault_window_check")
    if window_check_df is not None and "window_match" in window_check_df.columns:
        valid = window_check_df["window_match"].dropna()
        if len(valid) > 0:
            logger.info(
                "probe fault window match: %d/%d = %.1f%%",
                int(valid.sum()), len(valid), float(valid.mean()) * 100,
            )

    probe_inv_df = dfs.get("probe_invocation_join")
    if probe_inv_df is not None and "duration_match" in probe_inv_df.columns:
        all_match = bool(probe_inv_df["duration_match"].all())
        logger.info(
            "probe × invocation join: %d rows, all duration_match=%s",
            len(probe_inv_df), all_match,
        )

    paper_df = dfs.get("fault_model_paper_highlight")
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    self_check_df = dfs.get("fault_model_self_check")
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
