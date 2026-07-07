"""
文件作用：faas-sim 实验结果分析样例。

本样例演示如何统一读取多个仿真 run 的 CSV 输出，并生成标准化 summary 指标。
默认优先分析 examples/14_batch_experiment/outputs/，如果不存在，则使用本样例自带 sample_results。

运行方式：
    python -u examples/15_experiment_analysis/main.py

也可以指定输入输出目录：
    python -u examples/15_experiment_analysis/main.py --input-dir examples/14_batch_experiment/outputs
    python -u examples/15_experiment_analysis/main.py --output-dir examples/15_experiment_analysis/outputs
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from aggregation import (
    aggregate_by_policy_workload,
    build_paper_highlight,
    build_policy_comparison,
)
from config import build_config
from loaders import load_all_runs
from metrics import build_run_metrics
from report import generate_report
from self_check import log_self_check, self_check

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


def parse_args():
    """
    解析命令行参数。
    """
    parser = argparse.ArgumentParser(description="Analyze faas-sim experiment outputs.")
    parser.add_argument("--input-dir", default=None, help="实验结果输入目录。")
    parser.add_argument("--output-dir", default=None, help="分析结果输出目录。")
    return parser.parse_args()


def main():
    """
    experiment_analysis 样例入口。
    """
    configure_logging()
    args = parse_args()

    config = build_config(
        current_file=Path(__file__),
        input_dir=args.input_dir,
        output_dir=args.output_dir,
    )

    logger.info("analysis input_dir=%s", config.input_dir)
    logger.info("analysis output_dir=%s", config.output_dir)
    logger.info("analysis source_name=%s", config.source_name)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    runs = load_all_runs(config.input_dir)

    if not runs:
        raise RuntimeError(
            f"没有发现可分析的 run 目录：{config.input_dir}。"
            "请先运行 examples/14_batch_experiment/main.py，或检查 sample_results 是否存在。"
        )

    run_metrics = [build_run_metrics(run) for run in runs]
    run_metrics_df = pd.DataFrame(run_metrics)

    run_metrics_path = config.output_dir / "experiment_run_metrics.csv"
    run_metrics_df.to_csv(run_metrics_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", run_metrics_path)

    summary_df = aggregate_by_policy_workload(run_metrics_df)
    summary_path = config.output_dir / "experiment_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    comparison_df = build_policy_comparison(summary_df, baseline_policy="default_skippy")
    comparison_path = config.output_dir / "experiment_policy_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    # 论文 demo 关键摘要（与 14 的 batch_paper_highlight 风格一致）
    paper_highlight_df = build_paper_highlight(run_metrics_df, summary_df, comparison_df)
    paper_highlight_path = config.output_dir / "experiment_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    report_path = generate_report(
        output_dir=config.output_dir,
        source_name=config.source_name,
        input_dir=config.input_dir,
        run_metrics_df=run_metrics_df,
        summary_df=summary_df,
        comparison_df=comparison_df,
        paper_highlight_df=paper_highlight_df,
    )
    logger.info("saved %s", report_path)

    # 数据自洽段（与 14 的 self_check_batch_results 风格一致）
    self_check_result = self_check(
        run_metrics_df, summary_df, comparison_df, paper_highlight_df,
    )
    log_self_check(self_check_result)

    logger.info("experiment run metrics:\n%s", run_metrics_df.to_string(index=False))
    logger.info("experiment summary:\n%s", summary_df.to_string(index=False))
    logger.info("outputs saved to %s", config.output_dir)


if __name__ == "__main__":
    main()
