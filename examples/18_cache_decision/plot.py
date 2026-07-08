"""
文件作用：cache_decision 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_decision_distribution.png/pdf：
  4 类决策的函数计数柱状图（keep_warm / prewarm_candidate / eviction_candidate / observe）。
  论文 demo 关键图 —— 视觉证明决策分布与论文 sample 一致。
- fig02_utility_score_ranking.png/pdf：
  7 个函数按 utility_score 降序的横向条形图，颜色按 decision 类型。
  论文 demo 关键图 —— 展示哪些函数最值得保护。
- fig03_capacity_budget_utilization.png/pdf：
  选中 keep_warm/prewarm 的 memory 占用柱状图（vs capacity_budget_total 参考线）。
  论文 demo 关键图 —— capacity budget 100% 利用。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：18_cache_decision/outputs/ 目录下的 CSV
输出：18_cache_decision/figures/ 目录下的 png + pdf

运行：
    python -u examples/18_cache_decision/plot.py
"""

import argparse
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


FIGURE_DPI = 150
FIGURE_FORMAT = ["png", "pdf"]


DECISION_COLORS = {
    "keep_warm": "#2ca02c",
    "prewarm_candidate": "#ff7f0e",
    "eviction_candidate": "#d62728",
    "observe": "#7f7f7f",
}
DECISION_ORDER = ["keep_warm", "prewarm_candidate", "eviction_candidate", "observe"]


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "decision_count": "decision",
        "prewarm_candidate": "prewarm",
        "eviction_candidate": "eviction",
        "top_utility_rank": "top_util",
        "lowest_utility": "lowest_util",
        "capacity_budget": "budget",
        "decision_hint": "hint",
        "img-resize": "img",
        "json-parse": "json",
        "ml-infer": "ml",
        "report-gen": "report",
    }
    label = str(metric)
    for old, new in replacements.items():
        label = label.replace(old, new)
    return label.replace("__", " / ")


def configure_logging() -> None:
    """
    配置日志输出。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler()],
        force=True,
    )


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。
    """
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate paper-demo figures for 18_cache_decision.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/18_cache_decision/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/18_cache_decision/figures.",
    )
    return parser.parse_args()


def fig01_decision_distribution(decision_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    4 类决策的函数计数柱状图（论文 demo 关键图）。
    """
    if decision_df.empty or "decision" not in decision_df.columns:
        logger.warning("decision_df is empty; skip fig01")
        return None

    counts = []
    for dec in DECISION_ORDER:
        n = int((decision_df["decision"] == dec).sum())
        counts.append(n)

    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    colors = [DECISION_COLORS[d] for d in DECISION_ORDER]
    bars = ax.bar(
        DECISION_ORDER,
        counts,
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v}",
            ha="center",
            va="bottom",
        )
    ax.set_title("Cache decision distribution (keep_warm / prewarm / eviction / observe)")
    ax.set_xlabel("decision")
    ax.set_ylabel("function_count")
    ax.set_ylim(0, max(counts + [3]) * 1.2)
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_decision_distribution"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_utility_score_ranking(decision_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    7 个函数按 utility_score 降序的横向条形图，颜色按 decision 类型。
    """
    if decision_df.empty or "utility_score" not in decision_df.columns:
        logger.warning("decision_df is empty; skip fig02")
        return None

    df = decision_df.copy()
    if "decision" not in df.columns:
        df["decision"] = "observe"
    df["__order__"] = df["decision"].apply(
        lambda d: DECISION_ORDER.index(d) if d in DECISION_ORDER else len(DECISION_ORDER)
    )
    df = df.sort_values("utility_score", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    colors = [DECISION_COLORS.get(d, "#7f7f7f") for d in df["decision"]]
    bars = ax.barh(
        df["function_name"],
        df["utility_score"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v, dec in zip(bars, df["utility_score"], df["decision"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{v:.2f} ({dec})",
            ha="left",
            va="center",
            fontsize=8,
        )
    ax.set_title("Utility score ranking (by decision type)")
    ax.set_xlabel("utility_score = cold_benefit / resource_cost")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig02_utility_score_ranking"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_capacity_budget_utilization(
    decision_df: pd.DataFrame,
    paper_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    选中 keep_warm/prewarm 的 memory 占用柱状图（vs capacity_budget_total 参考线）。
    """
    if decision_df.empty or "selected_by_budget" not in decision_df.columns:
        logger.warning("decision_df is empty; skip fig03")
        return None

    selected = decision_df[decision_df["selected_by_budget"] == True]  # noqa: E712
    if selected.empty:
        logger.warning("no selected functions; skip fig03")
        return None

    selected = selected.sort_values("priority", ascending=False).reset_index(drop=True)

    # 从 paper_df 读 capacity_budget_total
    capacity_budget_total = 0
    if not paper_df.empty and "metric" in paper_df.columns:
        hl_rows = paper_df[paper_df["metric"] == "capacity_budget_total"]
        if not hl_rows.empty:
            try:
                capacity_budget_total = int(hl_rows["value"].iloc[0])
            except Exception:
                capacity_budget_total = 0

    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    colors = [DECISION_COLORS.get(d, "#7f7f7f") for d in selected["decision"]]
    bars = ax.bar(
        selected["function_name"],
        selected["memory_units"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, selected["memory_units"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{int(v)}",
            ha="center",
            va="bottom",
        )
    # capacity_budget 参考线
    if capacity_budget_total > 0:
        ax.axhline(
            capacity_budget_total,
            color="black",
            linestyle="--",
            linewidth=1.0,
            alpha=0.6,
            label=f"capacity_budget = {capacity_budget_total}",
        )
    used_total = int(selected["memory_units"].sum())
    ax.set_title(
        f"Selected (keep_warm/prewarm) memory = {used_total} / {capacity_budget_total}"
    )
    ax.set_xlabel("function_name")
    ax.set_ylabel("memory_units")
    ax.tick_params(axis="x", rotation=15)
    ax.set_ylim(0, max(capacity_budget_total, used_total) + 1)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")

    out = out_dir / "fig03_capacity_budget_utilization"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标分组条形图。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    df = paper_df.copy()
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value_num"])
    if df.empty:
        logger.warning("no numeric metrics in paper highlight; skip fig04")
        return None

    count_mask = (
        df["metric"].str.startswith("total_")
        | df["metric"].str.startswith("decision_count__")
        | df["metric"].isin(["decision_hint_matched", "decision_hint_total"])
    )
    utility_mask = (
        df["metric"].str.startswith("top_utility_rank_")
        | df["metric"].str.startswith("lowest_utility__")
    )

    panels = [
        (df[count_mask], "Counts and decision mix", "#4c78a8"),
        (df[utility_mask], "Utility score highlights", "#59a14f"),
        (df[~(count_mask | utility_mask)], "Budget and consistency", "#f58518"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(21, 6.5), constrained_layout=True)
    for ax, (panel_df, title, color) in zip(axes, panels):
        panel_df = panel_df.sort_values("value_num", ascending=True)
        bars = ax.barh(panel_df["metric"].map(short_metric_label), panel_df["value_num"], color=color)
        for bar, v in zip(bars, panel_df["value_num"]):
            label = f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}"
            ax.text(
                bar.get_width(),
                bar.get_y() + bar.get_height() / 2,
                label,
                ha="left",
                va="center",
                fontsize=8,
            )
        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.grid(True, axis="x", alpha=0.3)
        ax.tick_params(axis="y", labelsize=8)

    fig.suptitle("Cache Decision Paper Highlight Metrics", fontsize=14)

    out = out_dir / "fig04_paper_highlight_metrics"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def main() -> None:
    """
    入口：读取 outputs/ 下的 CSV，输出 figures/ 下的 png+pdf。
    """
    configure_logging()
    args = parse_args()
    input_dir, output_dir = args.input_dir, args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("input=%s output=%s", input_dir, output_dir)

    decision_df = pd.read_csv(input_dir / "cache_decision_detail.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "cache_decision_paper_highlight.csv", encoding="utf-8-sig")

    fig01_decision_distribution(decision_df, output_dir)
    fig02_utility_score_ranking(decision_df, output_dir)
    fig03_capacity_budget_utilization(decision_df, paper_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
