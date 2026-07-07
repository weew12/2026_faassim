"""
文件作用：faas-sim 缓存状态感知扩缩容样例。

本样例演示如何组合 R_cache 和 R_load：

R_desired = max(R_cache, R_load)

其中 R_cache 来自冷启动感知函数实例缓存收益，R_load 来自当前请求负载需求。
样例只生成扩缩容决策与控制计划，不直接调用 faas-sim 的真实扩缩容执行器。

运行方式：
    python -u examples/20_cache_aware_autoscaling/main.py
"""

import logging
import sys
from pathlib import Path

# 兼容使用绝对路径直接运行本文件的情况。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis import export_outputs
from autoscaler import CacheAwareAutoscaler
from loader import load_function_states
from models import AutoscalingConfig

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
    cache_aware_autoscaling 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    input_path = root_dir / "inputs" / "function_state_timeseries.csv"
    output_dir = root_dir / "outputs"

    logger.info("loading function state timeseries: %s", input_path)
    states = load_function_states(input_path)

    config = AutoscalingConfig(
        target_utilization=0.70,
        cache_utility_threshold=1.00,
        idle_age_threshold=6.0,
        cache_capacity_budget_units=5,
        min_replicas=0,
        max_replicas=5,
        resource_weight=0.60,
    )

    logger.info(
        "evaluating cache-aware autoscaling states=%d cache_budget=%d",
        len(states),
        config.cache_capacity_budget_units,
    )

    autoscaler = CacheAwareAutoscaler(config)
    decisions = autoscaler.evaluate(states)
    control_plans = autoscaler.build_control_plans(decisions)

    outputs = export_outputs(decisions, control_plans, output_dir, config=config)

    decision_df = outputs.get("cache_aware_autoscaling_decision")
    if decision_df is not None and len(decision_df) > 0:
        logger.info("cache aware autoscaling decisions:\n%s", decision_df.to_string(index=False))

    action_summary_df = outputs.get("cache_aware_autoscaling_action_summary")
    if action_summary_df is not None and len(action_summary_df) > 0:
        logger.info("cache aware autoscaling action summary:\n%s", action_summary_df.to_string(index=False))

    time_summary_df = outputs.get("cache_aware_autoscaling_time_summary")
    if time_summary_df is not None and len(time_summary_df) > 0:
        logger.info("cache aware autoscaling time summary:\n%s", time_summary_df.to_string(index=False))

    paper_highlight_df = outputs.get("cache_aware_autoscaling_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：R_cache vs R_load 主导 + 容量预算利用
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("r_load_dominant_ratio") or metric.startswith("cache_budget_utilization"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("action_count__") or metric.startswith("r_load_dominant_events"):
                logger.info("paper highlight: %s = %s", metric, value)
            elif metric.startswith("decision_plan_consistency"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
