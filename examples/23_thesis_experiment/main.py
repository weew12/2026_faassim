"""
文件作用：faas-sim 论文实验组织样例。

本样例用于形成一个最小但完整的论文实验闭环：
- 输入：函数画像、节点状态、请求 trace、实验 case；
- 策略：LoadOnly、FaasCache、CacheAwareJoint；
- 指标：请求延迟、冷启动惩罚、缓存命中率、R_cache/R_load/R_desired、控制动作；
- 输出：CSV 结果和 Markdown 实验报告。

运行方式：
    python -u examples/23_thesis_experiment/main.py
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
    load_experiment_cases,
    load_function_profiles,
    load_nodes,
    load_workload,
)
from runner import ThesisExperimentRunner

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
    thesis_experiment 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    input_dir = root_dir / "inputs"
    output_dir = root_dir / "outputs"

    logger.info("loading function profiles")
    profiles = load_function_profiles(input_dir / "function_profile.csv")

    logger.info("loading node states")
    nodes = load_nodes(input_dir / "node_state.csv")

    logger.info("loading workload trace")
    workload = load_workload(input_dir / "workload_trace.csv")

    logger.info("loading experiment cases")
    cases = load_experiment_cases(input_dir / "experiment_cases.csv")

    logger.info(
        "running thesis experiment cases=%d functions=%d nodes=%d requests=%d",
        len(cases),
        len(profiles),
        len(nodes),
        len(workload),
    )

    runner = ThesisExperimentRunner(
        cases=cases,
        profiles=profiles,
        nodes=nodes,
        workload=workload,
    )
    raw_outputs = runner.run()
    outputs = export_outputs(raw_outputs, output_dir)

    summary_df = outputs.get("thesis_policy_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("thesis policy summary:\n%s", summary_df.to_string(index=False))

    comparison_df = outputs.get("thesis_baseline_comparison")
    if comparison_df is not None and len(comparison_df) > 0:
        logger.info("thesis baseline comparison:\n%s", comparison_df.to_string(index=False))

    paper_highlight_df = outputs.get("thesis_paper_highlight")
    if paper_highlight_df is not None and len(paper_highlight_df) > 0:
        # 论文 demo 关键：CacheAwareJoint vs LoadOnly / FaasCache 提升
        for _, row in paper_highlight_df.iterrows():
            metric = row["metric"]
            value = row["value"]
            if metric.startswith("avg_latency_reduction") or metric.startswith("cold_start_penalty_reduction"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("image_cache_hit_rate_improvement") or metric.startswith("data_cache_hit_rate_improvement"):
                logger.info("paper highlight: %s = %.4f", metric, float(value))
            elif metric.startswith("warm_hit_rate__") or metric.startswith("r_dominant_summary"):
                logger.info("paper highlight: %s = %s", metric, value)

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
