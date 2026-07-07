"""
文件作用：faas-sim 冷启动感知函数实例保活策略样例。

本样例将函数实例 warm 状态抽象为有限容量缓存，并比较：
- 固定 keep-alive 策略；
- 冷启动感知 keep-alive 策略。

运行方式：
    python -u examples/21_cold_start_aware_policy/main.py
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
    load_function_profiles,
    load_request_trace,
)
from policies import build_default_policies
from runner import ColdStartAwarePolicyRunner

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
    cold_start_aware_policy 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    profile_path = root_dir / "inputs" / "function_profile.csv"
    trace_path = root_dir / "inputs" / "request_trace.csv"
    output_dir = root_dir / "outputs"

    capacity_units = 4

    logger.info("loading function profile: %s", profile_path)
    profiles = load_function_profiles(profile_path)

    logger.info("loading request trace: %s", trace_path)
    requests = load_request_trace(trace_path)

    logger.info("creating policies capacity_units=%d", capacity_units)
    policies = build_default_policies(
        profiles=profiles,
        capacity_units=capacity_units,
    )

    logger.info("running cold-start-aware policy experiment requests=%d policies=%d", len(requests), len(policies))
    runner = ColdStartAwarePolicyRunner(
        profiles=profiles,
        requests=requests,
        policies=policies,
    )

    raw_outputs = runner.run()
    outputs = export_outputs(raw_outputs, output_dir)

    summary_df = outputs.get("cold_start_policy_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("cold start policy summary:\n%s", summary_df.to_string(index=False))

    function_summary_df = outputs.get("cold_start_function_summary")
    if function_summary_df is not None and len(function_summary_df) > 0:
        logger.info("cold start function summary:\n%s", function_summary_df.to_string(index=False))

    paper_highlight_df = outputs.get("cold_start_policy_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：cold_start_aware vs fixed_keep_alive 提升
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("hit_rate_ratio") or metric.startswith("hit_rate_improvement"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("cold_start_penalty_reduction") or metric.startswith("latency_reduction"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("hit_rate__") or metric.startswith("total_cold_start_penalty__"):
                logger.info("paper highlight: %s = %s", metric, value)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
