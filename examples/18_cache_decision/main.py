"""
文件作用：faas-sim 冷启动感知缓存决策样例。

本样例从函数画像快照读取当前状态，计算冷启动收益、资源代价和缓存效用，
并生成 keep_warm、prewarm_candidate、eviction_candidate 和 observe 四类缓存决策。

运行方式：
    python -u examples/18_cache_decision/main.py
"""

import logging
import sys
from pathlib import Path

from advisor import CacheDecisionAdvisor
from analysis import export_outputs
from decision_model import CacheDecisionConfig
from profiles import load_profiles

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
    cache_decision 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    profile_path = root_dir / "inputs" / "function_profile_snapshot.csv"
    output_dir = root_dir / "outputs"

    config = CacheDecisionConfig(
        capacity_budget_units=4,
        keep_warm_threshold=1.20,
        prewarm_threshold=1.00,
        eviction_threshold=0.35,
        idle_age_threshold=6.0,
        resource_weight=0.60,
    )

    logger.info("loading function profiles: %s", profile_path)
    profiles = load_profiles(profile_path)

    logger.info("evaluating cache decisions profiles=%d budget=%d", len(profiles), config.capacity_budget_units)
    advisor = CacheDecisionAdvisor(config)
    decisions = advisor.evaluate(profiles)
    hints = advisor.build_control_hints(decisions)

    outputs = export_outputs(decisions, hints, output_dir, config=config)

    detail_df = outputs.get("cache_decision_detail")
    if detail_df is not None and len(detail_df) > 0:
        logger.info("cache decision detail:\n%s", detail_df.to_string(index=False))

    summary_df = outputs.get("cache_decision_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("cache decision summary:\n%s", summary_df.to_string(index=False))

    rank_df = outputs.get("cache_decision_rank")
    if rank_df is not None and len(rank_df) > 0:
        logger.info("cache decision rank:\n%s", rank_df.to_string(index=False))

    paper_highlight_df = outputs.get("cache_decision_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：决策分布 + utility top-3 + capacity budget 利用
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("decision_count__") or metric.startswith("top_utility"):
                logger.info("paper highlight: %s = %s", metric, value)
            elif metric.startswith("capacity_budget"):
                logger.info("paper highlight: %s = %s", metric, value)
            elif metric.startswith("decision_hint_consistency"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))

    # data self-check 汇总（仿 02-17 模式）
    self_check_df = outputs.get("cache_decision_self_check")
    if self_check_df is not None and len(self_check_df) > 0:
        if "passed" in self_check_df.columns:
            n_pass = int(self_check_df["passed"].sum())
        else:
            n_pass = 0
        if "status" in self_check_df.columns:
            n_fail = int((self_check_df["status"] == "FAIL").sum())
        else:
            n_fail = 0
        n_total = len(self_check_df)
        logger.info("data self-check: %d / %d PASS", n_pass, n_total)
        if n_fail > 0:
            for _, row in self_check_df[self_check_df.get("status") == "FAIL"].iterrows():
                logger.warning("  FAILED: %s", row.get("name", ""))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
