"""
文件作用：批量实验执行器。

该文件负责把 ExperimentCase 转换为一次完整 faas-sim Simulation。
"""

import logging
import random
from pathlib import Path

import ether.scenarios.urbansensing as scenario

from sim.faassim import Simulation
from sim.topology import Topology

from analysis import export_case_outputs
from benchmark import BatchExperimentBenchmark
from experiment_config import ExperimentCase
from scheduler import FixedNodeScheduler
from simulator import BatchExperimentSimulatorFactory

logger = logging.getLogger(__name__)


def build_topology() -> Topology:
    """
    创建批量实验使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


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

    sim.create_simulator_factory = lambda: BatchExperimentSimulatorFactory(case)

    sim.run()

    return export_case_outputs(sim, case, output_dir)
