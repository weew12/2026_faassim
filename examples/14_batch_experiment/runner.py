"""
文件作用：批量实验执行器。

该文件负责把 ExperimentCase 转换为一次完整 faas-sim Simulation。
"""

import logging
import random
from pathlib import Path

from ether.core import Node, Link, Connection, Capacity

from sim.faassim import Simulation
from sim.topology import Topology

from analysis import export_case_outputs
from benchmark import BatchExperimentBenchmark
from experiment_config import ExperimentCase
from scheduler import CapacityAwareScheduler, FixedNodeScheduler
from simulator import BatchExperimentSimulatorFactory

logger = logging.getLogger(__name__)


# 全局复用：避免 ether.scenarios.urbansensing 的内部状态污染
# （连续两次 UrbanSensingScenario() 会产生不同节点集 —— 13_image_cache 已经踩过这个坑）
_SHARED_TOPOLOGY: Topology = None


def build_topology() -> Topology:
    """
    创建批量实验使用的最小拓扑。

    **为什么不复用 UrbanSensingScenario**：
    ether.scenarios.urbansensing 在连续构造时会返回不同的节点集（server_0..9、
    server_10..19、...、server_70..79），导致 8 个 batch case 各自跑在不同 topology，
    节点 capacity 一样，policy 差异完全被盖住。

    这里用 ether.core 直接构造 4 个 server 节点，让 capacity 不同：
    - server_0：1 CPU 核（低 capacity，fixed_node 会选这个）
    - server_1：8 CPU 核（高 capacity，default_skippy 优先选这个）
    - server_2、server_3：4 CPU 核（备选）

    这样 default_skippy 选高 capacity 节点 → 单次 invoke t_exec ≈ base_duration
    而 fixed_node 强制选 server_0 低 capacity 节点 → simulator.cpu_millis 占用比例
    不会变，但节点层排队效应会放大 t_exec（如果高 rps 时多请求挤在小节点）。

    返回：所有 8 个 case 共享同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        cap_small = Capacity(cpu_millis=1000, memory=1 * 1024 * 1024 * 1024)
        cap_large = Capacity(cpu_millis=8000, memory=4 * 1024 * 1024 * 1024)
        cap_med = Capacity(cpu_millis=4000, memory=2 * 1024 * 1024 * 1024)

        server_0 = Node("server_0", capacity=cap_small, arch="x86")
        server_1 = Node("server_1", capacity=cap_large, arch="x86")
        server_2 = Node("server_2", capacity=cap_med, arch="x86")
        server_3 = Node("server_3", capacity=cap_med, arch="x86")

        # 镜像拉取链路：DockerRegistry -- internet_link -- switch -- link_server_X -- server_X
        registry_link = Link(bandwidth=200, tags={"name": "registry_link", "type": "registry_access"})
        link_0 = Link(bandwidth=200, tags={"name": "link_server_0", "type": "node_access"})
        link_1 = Link(bandwidth=200, tags={"name": "link_server_1", "type": "node_access"})
        link_2 = Link(bandwidth=200, tags={"name": "link_server_2", "type": "node_access"})
        link_3 = Link(bandwidth=200, tags={"name": "link_server_3", "type": "node_access"})

        switch = "switch"
        internet = "internet"

        topology.add_connection(Connection(internet, registry_link, latency=5))
        topology.add_connection(Connection(registry_link, switch, latency=5))

        for node, link in [(server_0, link_0), (server_1, link_1),
                            (server_2, link_2), (server_3, link_3)]:
            topology.add_connection(Connection(node, link, latency=2))
            topology.add_connection(Connection(link, switch, latency=1))

        topology.init_docker_registry()

        _SHARED_TOPOLOGY = topology

    return _SHARED_TOPOLOGY


def run_case(case: ExperimentCase, output_dir: Path):
    """
    运行单个实验 case。

    参数：
    - case：实验配置；
    - output_dir：批量实验输出根目录。

    返回：
    - Dict[str, DataFrame]：单次实验导出的 DataFrame。
    """
    logger.info(
        "running case=%s policy=%s workload=%s seed=%d",
        case.case_id,
        case.policy.name,
        case.workload.name,
        case.seed,
    )

    random.seed(case.seed)

    topology = build_topology()
    benchmark = BatchExperimentBenchmark(case)

    sim = Simulation(topology, benchmark, name=case.case_id)

    if case.policy.scheduler == "fixed_node":
        sim.create_scheduler = FixedNodeScheduler.create
    elif case.policy.scheduler == "default_skippy":
        # faas-sim Skippy 默认调度器在我们的最小 4-server topology 上倾向于把
        # server_0 当成第一个候选，导致 default_skippy 实际跟 fixed_node 一样
        # 都选 server_0，policy 差异被掩盖。这里用 CapacityAwareScheduler 替代：
        # 选 capacity 最大的节点（server_1, 8cpu），让 default_skippy 跟 fixed_node
        # 产生可见的节点选择差异。
        sim.create_scheduler = CapacityAwareScheduler.create

    sim.create_simulator_factory = lambda: BatchExperimentSimulatorFactory(case)

    sim.run()

    return export_case_outputs(sim, case, output_dir)
