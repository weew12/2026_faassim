"""
文件作用：faas-sim 函数实例缓存策略样例。

本样例演示函数实例缓存策略的最小实验闭环：
- 从 request_trace.csv 读取请求序列；
- 根据函数冷启动代价与资源占用模拟缓存命中/未命中；
- 对比 FIFO、LRU 和 Utility-aware 三类策略；
- 导出请求级结果、驱逐事件、缓存状态和策略摘要。

运行方式：
    python -u examples/17_cache_policy/main.py
"""

import logging
import sys
from pathlib import Path

from analysis import export_outputs
from function_catalog import default_function_catalog
from policies import build_default_policies
from runner import CachePolicyExperimentRunner
from workload import load_request_trace

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
    cache_policy 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    trace_path = root_dir / "inputs" / "request_trace.csv"
    output_dir = root_dir / "outputs"

    cache_capacity_units = 4

    logger.info("loading request trace: %s", trace_path)
    requests = load_request_trace(trace_path)

    logger.info("loading function catalog")
    catalog = default_function_catalog()

    logger.info("creating cache policies capacity_units=%d", cache_capacity_units)
    policies = build_default_policies(
        capacity_units=cache_capacity_units,
        catalog=catalog,
    )

    logger.info("running cache policy experiment requests=%d policies=%d", len(requests), len(policies))
    runner = CachePolicyExperimentRunner(
        catalog=catalog,
        requests=requests,
        policies=policies,
    )

    raw_outputs = runner.run()
    outputs = export_outputs(raw_outputs, output_dir)

    policy_summary_df = outputs.get("cache_policy_summary")
    if policy_summary_df is not None and len(policy_summary_df) > 0:
        logger.info("cache policy summary:\n%s", policy_summary_df.to_string(index=False))

    function_summary_df = outputs.get("cache_function_summary")
    if function_summary_df is not None and len(function_summary_df) > 0:
        logger.info("cache function summary:\n%s", function_summary_df.to_string(index=False))

    paper_highlight_df = outputs.get("cache_policy_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：策略相对提升（以 fifo 为 baseline）
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("hit_rate_ratio") or metric.startswith("hit_rate_improvement"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("latency_reduction") or metric.startswith("cold_start_penalty_reduction"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("hit_rate__") or metric.startswith("total_cold_start_penalty__"):
                logger.info("paper highlight: %s = %s", metric, value)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
