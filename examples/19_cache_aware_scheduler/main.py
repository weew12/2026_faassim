"""
文件作用：faas-sim 缓存状态感知调度样例。

本样例演示调度器如何读取节点级函数 warm 缓存状态，并优先把函数调度到已有缓存的节点。
同时运行 cache_blind 和 cache_aware 两个场景，用于对比缓存命中率和冷启动惩罚。

运行方式：
    python -u examples/19_cache_aware_scheduler/main.py
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
from ether.core import Node, Link, Connection, Capacity

import pandas as pd

from sim.core import Environment
from sim.faassim import Simulation
from sim.topology import Topology

from analysis import (
    export_scenario_outputs,
    export_comparison,
    build_paper_highlight,
    self_check,
    log_self_check,
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


# 全局复用：避免 ether.scenarios.urbansensing 的内部状态污染
# （连续两次 UrbanSensingScenario() 会产生不同节点集 —— 13_image_cache 已经踩过这个坑）
# 两个 scenario 必须跑在**同一份 topology**上，cache snapshot 的 server_0/1/2 才能跟实际节点对得上。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建 cache_aware_scheduler 样例使用的最小 4-server 拓扑。

    **为什么不复用 UrbanSensingScenario**：
    ether.scenarios.urbansensing 在连续构造时会返回不同的节点集（server_0..9、
    server_10..19、...、server_70..79），导致 cache_blind 和 cache_aware 两个 scenario
    各自跑在不同 topology，cache snapshot 完全失效（server_0/1/2 对不上 server_10..19）。

    这里用 ether.core 直接构造 4 个 server 节点：
    - server_0：img-resize + json-parse 缓存
    - server_1：fft 缓存
    - server_2：ml-infer 缓存
    - server_3：无缓存（cache_blind 轮转会选它，cache_aware 会避开它）

    cache_aware 调度器读 cache snapshot → 给 server_0/1/2 高分（cache hit）→ 选有缓存的节点。
    cache_blind 调度器按 cursor 轮转 → 会选到 server_3（无缓存），触发冷启动。

    返回：两个 scenario 共享同一份 Topology 对象。
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
        logger.info("cache aware scheduler comparison:\n%s", comparison_df.to_string(index=False))

    # 论文 demo 关键摘要 + 数据自洽段
    scenario_probe_joins = {
        "cache_blind": blind_dfs.get("cache_aware_probe_invocation_join", pd.DataFrame()),
        "cache_aware": aware_dfs.get("cache_aware_probe_invocation_join", pd.DataFrame()),
    }
    paper_highlight_df = build_paper_highlight(comparison_df, scenario_probe_joins)
    paper_highlight_path = output_dir / "cache_aware_scheduler_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    # 数据自洽段
    cache_snapshot_df = cache_index.to_dataframe()
    self_check_result = self_check(
        comparison_df, scenario_probe_joins, paper_highlight_df,
        cache_snapshot_df, expected_request_count=len(workload),
    )
    log_self_check(self_check_result)

    # 导出 self_check 结果到 csv（沿用 02-18 模式）
    self_check_path = output_dir / "cache_aware_scheduler_self_check.csv"
    self_check_df = pd.DataFrame(self_check_result.get("checks") or [])
    self_check_df.to_csv(self_check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", self_check_path)

    # 论文 demo 关键 log
    if len(paper_highlight_df) > 0:
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("cache_hit_rate_ratio") or metric.startswith("cache_hit_rate_improvement"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("cold_start_penalty_reduction") or metric.startswith("avg_duration_reduction"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("cache_hit_rate__"):
                logger.info("paper highlight: %s = %s", metric, value)

    # data self-check 一句话总结（沿用 02-18 模式）
    n_pass = self_check_result.get("n_pass", 0)
    n_warn = self_check_result.get("n_warn", 0)
    n_fail = self_check_result.get("n_fail", 0)
    n_total = n_pass + n_warn + n_fail
    logger.info("data self-check: %d / %d PASS", n_pass, n_total)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
