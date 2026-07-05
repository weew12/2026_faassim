"""
文件作用：faas-sim 缓存状态感知调度样例。

本样例演示调度器如何读取节点级函数 warm 缓存状态，并优先把函数调度到已有缓存的节点。
同时运行 cache_blind 和 cache_aware 两个场景，用于对比缓存命中率和冷启动惩罚。

运行方式：
    python -u examples/cache_aware_scheduler/main.py
"""

import logging
import sys
from pathlib import Path
from typing import Callable

# 兼容直接使用绝对路径运行本文件的情况：
# 确保优先导入当前 faas-sim 项目目录中的 sim / ether / skippy，
# 避免误用用户环境 site-packages 中安装过的旧版本 sim 包。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ether.scenarios.urbansensing as scenario

from sim.core import Environment
from sim.faassim import Simulation
from sim.topology import Topology

from analysis import (
    export_scenario_outputs,
    export_comparison,
)
from benchmark import CacheAwareSchedulerBenchmark
from cache_state import load_cache_state
from scheduler import (
    CacheAwareScheduler,
    CacheBlindScheduler,
)
from simulator import CacheAwareSimulatorFactory
from workload import load_workload

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
    创建 cache_aware_scheduler 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


def run_scenario(
    scenario_name: str,
    scheduler_factory: Callable[[Environment], object],
    cache_index,
    workload,
    output_dir: Path,
):
    """
    运行一个调度场景。
    """
    logger.info("running scenario=%s", scenario_name)

    topology = example_topology()
    benchmark = CacheAwareSchedulerBenchmark(
        scenario_name=scenario_name,
        workload=workload,
    )

    sim = Simulation(topology, benchmark, name=scenario_name)
    sim.create_scheduler = scheduler_factory
    sim.create_simulator_factory = lambda: CacheAwareSimulatorFactory(
        scenario_name=scenario_name,
        cache_index=cache_index,
    )

    sim.run()

    dfs = export_scenario_outputs(sim, scenario_name, output_dir)
    return dfs


def main():
    """
    cache_aware_scheduler 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    cache_path = root_dir / "inputs" / "cache_state_snapshot.csv"
    workload_path = root_dir / "inputs" / "workload.csv"
    output_dir = root_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("loading cache state: %s", cache_path)
    cache_index = load_cache_state(cache_path)

    logger.info("loading workload: %s", workload_path)
    workload = load_workload(workload_path)

    # 导出输入缓存快照，便于与调度结果对应。
    cache_index.to_dataframe().to_csv(
        output_dir / "cache_state_snapshot.csv",
        index=False,
        encoding="utf-8-sig",
    )

    scenario_summaries = []

    blind_dfs = run_scenario(
        scenario_name="cache_blind",
        scheduler_factory=CacheBlindScheduler.create,
        cache_index=cache_index,
        workload=workload,
        output_dir=output_dir,
    )
    scenario_summaries.append(blind_dfs["cache_aware_scheduler_summary"])

    aware_dfs = run_scenario(
        scenario_name="cache_aware",
        scheduler_factory=lambda env: CacheAwareScheduler.create(env, cache_index),
        cache_index=cache_index,
        workload=workload,
        output_dir=output_dir,
    )
    scenario_summaries.append(aware_dfs["cache_aware_scheduler_summary"])

    comparison_df = export_comparison(output_dir, scenario_summaries)

    if comparison_df is not None and len(comparison_df) > 0:
        logger.info("cache aware scheduler comparison:\\n%s", comparison_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
