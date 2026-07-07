"""
文件作用：faas-sim 边缘缓存感知调度样例。

本样例不直接调用 faas-sim 核心调度器，而是用独立的调度逻辑演示边缘缓存状态如何进入调度评分。
这样可以避免不同 faas-sim 源码版本的接口差异影响样例运行。

运行方式：
    python -u examples/22_edge_cache_scheduler/main.py
"""

import logging
import sys
from pathlib import Path

# 兼容使用绝对路径直接运行本文件的情况。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis import export_outputs
from loader import (
    load_cache_entries,
    load_nodes,
    load_profiles,
    load_requests,
)
from runner import EdgeCacheSchedulerRunner

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


def main():
    """
    edge_cache_scheduler 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    input_dir = root_dir / "inputs"
    output_dir = root_dir / "outputs"

    logger.info("loading node state")
    nodes = load_nodes(input_dir / "node_state_snapshot.csv")

    logger.info("loading function profiles")
    profiles = load_profiles(input_dir / "function_profile.csv")

    logger.info("loading cache state")
    cache_entries = load_cache_entries(input_dir / "cache_state_snapshot.csv")

    logger.info("loading request trace")
    requests = load_requests(input_dir / "request_trace.csv")

    logger.info(
        "running edge cache scheduler experiment nodes=%d functions=%d cache_entries=%d requests=%d",
        len(nodes),
        len(profiles),
        len(cache_entries),
        len(requests),
    )

    runner = EdgeCacheSchedulerRunner(
        nodes=nodes,
        profiles=profiles,
        cache_entries=cache_entries,
        requests=requests,
    )
    raw_outputs = runner.run()
    outputs = export_outputs(raw_outputs, output_dir)

    summary_df = outputs.get("edge_cache_policy_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("edge cache policy summary:\n%s", summary_df.to_string(index=False))

    function_summary_df = outputs.get("edge_cache_function_summary")
    if function_summary_df is not None and len(function_summary_df) > 0:
        logger.info("edge cache function summary:\n%s", function_summary_df.to_string(index=False))

    paper_highlight_df = outputs.get("edge_cache_policy_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：edge_cache_aware vs edge_round_robin 提升
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("function_cache_hit_rate_improvement") or metric.startswith("image_cache_hit_rate_improvement") or metric.startswith("data_cache_hit_rate_improvement"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("avg_estimated_latency_reduction") or metric.startswith("cold_start_penalty_reduction"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("function_cache_hit_rate__") or metric.startswith("avg_estimated_latency__"):
                logger.info("paper highlight: %s = %s", metric, value)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
