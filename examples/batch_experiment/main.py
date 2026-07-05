"""
文件作用：faas-sim 批量实验样例。

本样例演示如何组织多策略、多负载、多随机种子的批量仿真实验，包括：
- 生成实验组合；
- 循环运行每个实验 case；
- 每个 case 独立导出原始指标；
- 汇总生成 batch_results.csv 和 batch_summary.csv。

运行方式：
    python -u examples/batch_experiment/main.py
"""

import logging
import sys
from pathlib import Path

from analysis import export_batch_results
from experiment_config import (
    default_batch_config,
    build_experiment_cases,
)
from progress import progress_iter
from runner import run_case

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
    batch_experiment 样例入口。
    """
    configure_logging()

    output_dir = Path(__file__).resolve().parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = default_batch_config()
    cases = build_experiment_cases(config)

    logger.info("batch experiment cases=%d", len(cases))

    case_results = []

    for case in progress_iter(cases, total=len(cases), description="batch_experiment"):
        dfs = run_case(case, output_dir)
        case_results.append(dfs["case_result"])

    outputs = export_batch_results(output_dir, case_results)

    batch_results_df = outputs.get("batch_results")
    if batch_results_df is not None and len(batch_results_df) > 0:
        logger.info("batch results:\\n%s", batch_results_df.to_string(index=False))

    batch_summary_df = outputs.get("batch_summary")
    if batch_summary_df is not None and len(batch_summary_df) > 0:
        logger.info("batch summary:\\n%s", batch_summary_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
