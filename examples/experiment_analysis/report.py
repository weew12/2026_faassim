"""
文件作用：生成 Markdown 分析报告。

报告用于快速查看实验输入、run 数量、聚合摘要和策略对比结论。
"""

from pathlib import Path

import pandas as pd


def dataframe_to_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    """
    将 DataFrame 转为 Markdown 表格。

    如果 tabulate 不可用，则回退为普通 CSV 文本块。
    """
    if df is None or df.empty:
        return "无数据。"

    preview = df.head(max_rows)

    try:
        return preview.to_markdown(index=False)
    except Exception:
        return "```text\n" + preview.to_csv(index=False) + "```"


def generate_report(
    output_dir: Path,
    source_name: str,
    input_dir: Path,
    run_metrics_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
):
    """
    生成 Markdown 报告。
    """
    report_path = output_dir / "experiment_analysis_report.md"

    lines = [
        "# experiment_analysis 实验结果分析报告",
        "",
        "## 1. 输入信息",
        "",
        f"- source_name：`{source_name}`",
        f"- input_dir：`{input_dir}`",
        f"- run_count：`{len(run_metrics_df)}`",
        "",
        "## 2. Run-level 结果预览",
        "",
        dataframe_to_markdown(run_metrics_df),
        "",
        "## 3. Policy / Workload 聚合摘要",
        "",
        dataframe_to_markdown(summary_df),
        "",
        "## 4. 策略对比结果",
        "",
        dataframe_to_markdown(comparison_df),
        "",
        "## 5. 说明",
        "",
        "本报告由 `examples/experiment_analysis/main.py` 自动生成。"
        "默认情况下，脚本优先读取 `examples/batch_experiment/outputs/`，"
        "如果该目录不存在，则读取本样例自带的 `sample_results/`。",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
