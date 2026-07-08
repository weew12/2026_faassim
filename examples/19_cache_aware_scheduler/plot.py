"""
文件作用：cache_aware_scheduler 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_cache_blind_vs_aware_metrics.png/pdf（论文 demo 关键图）：
  3 个核心 metric (cache_hit_rate / avg_final_duration / total_cold_start_penalty)
  × 2 个 scenario (cache_blind / cache_aware) 的分组柱状图。
- fig02_per_function_cache_hit_rate.png/pdf：
  4 函数 × 2 scenario 的 cache_hit_rate 分组柱状图 + 冷启动惩罚折线。
- fig03_cache_aware_candidate_score_heatmap.png/pdf：
  4 函数 × 4 节点 (server_0/1/2/3) 的 cache_aware scheduler total_score 热力图。
  论文 demo 关键图 —— 展示 cache_aware scheduler 怎么挑 node（每个函数都选 score 最高的节点）。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：19_cache_aware_scheduler/outputs/ 目录下的 CSV
输出：19_cache_aware_scheduler/figures/ 目录下的 png + pdf

运行：
    python -u examples/19_cache_aware_scheduler/plot.py
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


SCENARIO_COLORS = {
    "cache_blind": "#7f7f7f",
    "cache_aware": "#2ca02c",
}


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "cache_aware": "aware",
        "cache_blind": "blind",
        "cache_hit_rate": "hit_rate",
        "cache_hit_count": "hit_count",
        "avg_final_duration": "avg_duration",
        "total_cold_start_penalty": "cold_penalty",
        "cold_start_penalty_reduction": "cold_reduction",
        "avg_duration_reduction": "duration_reduction",
        "probe_invocation_duration_match": "duration_match",
        "probe_invocation_simtime_match": "simtime_match",
        "selected_nodes_count": "node_count",
        "_over_": " over ",
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
        description="Generate paper-demo figures for 19_cache_aware_scheduler.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/19_cache_aware_scheduler/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/19_cache_aware_scheduler/figures.",
    )
    return parser.parse_args()


def fig01_cache_blind_vs_aware_metrics(
    comparison_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 个核心 metric × 2 个 scenario 的分组柱状图（论文 demo 关键图）。
    """
    if comparison_df.empty:
        logger.warning("comparison_df is empty; skip fig01")
        return None

    metrics = [
        ("cache_hit_rate", "cache_hit_rate"),
        ("avg_final_duration", "avg_final_duration (s)"),
        ("total_cold_start_penalty", "total_cold_start_penalty (s)"),
    ]
    scenarios = ["cache_blind", "cache_aware"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), constrained_layout=True)

    for ax, (col, label) in zip(axes, metrics):
        values = []
        for sc in scenarios:
            row = comparison_df[comparison_df["scenario"] == sc]
            v = float(row[col].iloc[0]) if (not row.empty and col in row.columns) else 0.0
            values.append(v)

        bars = ax.bar(
            scenarios,
            values,
            color=[SCENARIO_COLORS[sc] for sc in scenarios],
            edgecolor="black",
            linewidth=0.5,
        )
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v:.3f}" if v < 10 else f"{v:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.set_title(label, fontsize=10)
        ax.set_ylabel(label)
        ax.set_ylim(0, max(values + [0.1]) * 1.2)
        ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "Cache-blind vs cache-aware scheduler (3 key metrics)",
        fontsize=12,
        fontweight="bold",
    )

    out = out_dir / "fig01_cache_blind_vs_aware_metrics"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_function_cache_hit_rate(
    blind_fn_df: pd.DataFrame,
    aware_fn_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    4 函数 × 2 scenario 的 cache_hit_rate 分组柱状图（叠加冷启动惩罚折线）。
    """
    if blind_fn_df.empty or aware_fn_df.empty:
        logger.warning("function summary df is empty; skip fig02")
        return None

    # 取两个 scenario 的函数并集
    all_fns = sorted(set(blind_fn_df["function_name"]) | set(aware_fn_df["function_name"]))

    blind_hit = []
    aware_hit = []
    blind_cold = []
    aware_cold = []
    for fn in all_fns:
        b = blind_fn_df[blind_fn_df["function_name"] == fn]
        a = aware_fn_df[aware_fn_df["function_name"] == fn]
        blind_hit.append(float(b["cache_hit_rate"].iloc[0]) if not b.empty else 0.0)
        aware_hit.append(float(a["cache_hit_rate"].iloc[0]) if not a.empty else 0.0)
        blind_cold.append(float(b["total_cold_start_penalty"].iloc[0]) if not b.empty else 0.0)
        aware_cold.append(float(a["total_cold_start_penalty"].iloc[0]) if not a.empty else 0.0)

    fig, ax1 = plt.subplots(figsize=(9, 5), constrained_layout=True)

    x = np.arange(len(all_fns))
    width = 0.35

    bars1 = ax1.bar(
        x - width / 2,
        blind_hit,
        width,
        color=SCENARIO_COLORS["cache_blind"],
        edgecolor="black",
        linewidth=0.5,
        label="cache_hit_rate (cache_blind)",
    )
    bars2 = ax1.bar(
        x + width / 2,
        aware_hit,
        width,
        color=SCENARIO_COLORS["cache_aware"],
        edgecolor="black",
        linewidth=0.5,
        label="cache_hit_rate (cache_aware)",
    )
    for bar, v in zip(bars1, blind_hit):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    for bar, v in zip(bars2, aware_hit):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(all_fns, rotation=15, ha="right")
    ax1.set_ylabel("cache_hit_rate (0-1)")
    ax1.set_ylim(0, 1.2)
    ax1.set_xlabel("function_name")
    ax1.grid(True, axis="y", alpha=0.3)
    ax1.legend(loc="upper left")

    # 折线：total_cold_start_penalty（双轴）
    ax2 = ax1.twinx()
    ax2.plot(
        x,
        blind_cold,
        marker="o",
        color=SCENARIO_COLORS["cache_blind"],
        linestyle="--",
        label="cold_penalty (cache_blind)",
        alpha=0.7,
    )
    ax2.plot(
        x,
        aware_cold,
        marker="s",
        color=SCENARIO_COLORS["cache_aware"],
        linestyle="--",
        label="cold_penalty (cache_aware)",
        alpha=0.7,
    )
    ax2.set_ylabel("total_cold_start_penalty (s)")
    ax2.legend(loc="upper right")

    ax1.set_title("Per-function cache hit rate (bar) + cold start penalty (line)")

    out = out_dir / "fig02_per_function_cache_hit_rate"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cache_aware_candidate_score_heatmap(
    candidate_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    4 函数 × 4 节点的 cache_aware scheduler total_score 热力图（论文 demo 关键图）。

    每个 function 对 4 个 candidate_node 的 total_score。
    论文 demo 关键图：展示 cache_aware scheduler 怎么挑 node（每个函数都选 score 最高的节点）。
    """
    if candidate_df.empty:
        logger.warning("candidate_df is empty; skip fig03")
        return None

    # 取每个 (function, candidate_node) 第一次出现的 total_score（避免重复）
    df = candidate_df.drop_duplicates(subset=["function_name", "candidate_node"], keep="first")
    functions = sorted(df["function_name"].unique())
    nodes = sorted(df["candidate_node"].unique())

    matrix = np.zeros((len(functions), len(nodes)))
    for i, fn in enumerate(functions):
        for j, nd in enumerate(nodes):
            row = df[(df["function_name"] == fn) & (df["candidate_node"] == nd)]
            v = float(row["total_score"].iloc[0]) if not row.empty else 0.0
            matrix[i, j] = v

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    im = ax.imshow(matrix, cmap="YlGn", aspect="auto", vmin=0)

    # 单元格内标注 total_score
    for i in range(len(functions)):
        for j in range(len(nodes)):
            v = matrix[i, j]
            color = "white" if v > matrix.max() * 0.6 else "black"
            ax.text(
                j,
                i,
                f"{v:.2f}",
                ha="center",
                va="center",
                color=color,
                fontsize=10,
            )

    ax.set_xticks(np.arange(len(nodes)))
    ax.set_yticks(np.arange(len(functions)))
    ax.set_xticklabels(nodes, rotation=15, ha="right")
    ax.set_yticklabels(functions)
    ax.set_xlabel("candidate_node")
    ax.set_ylabel("function_name")
    ax.set_title("Cache-aware scheduler: total_score per (function, candidate_node)")
    fig.colorbar(im, ax=ax, label="total_score")

    out = out_dir / "fig03_cache_aware_candidate_score_heatmap"
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

    scenario_mask = (
        df["metric"].str.startswith("cache_hit_rate__")
        | df["metric"].str.startswith("cache_hit_count__")
        | df["metric"].str.startswith("avg_final_duration__")
        | df["metric"].str.startswith("total_cold_start_penalty__")
    )
    consistency_mask = (
        df["metric"].str.startswith("probe_invocation_")
        | df["metric"].str.startswith("selected_nodes_count__")
    )
    improvement_mask = ~(scenario_mask | consistency_mask)

    panels = [
        (df[scenario_mask], "Scenario metrics", "#4c78a8"),
        (df[improvement_mask], "Relative improvements", "#f58518"),
        (df[consistency_mask], "Join and node checks", "#59a14f"),
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

    fig.suptitle("Cache-aware Scheduler Paper Highlight Metrics", fontsize=14)

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

    comparison_df = pd.read_csv(input_dir / "cache_aware_scheduler_comparison.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "cache_aware_scheduler_paper_highlight.csv", encoding="utf-8-sig")
    blind_fn_df = pd.read_csv(
        input_dir / "cache_blind" / "cache_aware_function_summary.csv", encoding="utf-8-sig",
    )
    aware_fn_df = pd.read_csv(
        input_dir / "cache_aware" / "cache_aware_function_summary.csv", encoding="utf-8-sig",
    )
    candidate_df = pd.read_csv(
        input_dir / "cache_aware" / "cache_aware_candidate.csv", encoding="utf-8-sig",
    )

    fig01_cache_blind_vs_aware_metrics(comparison_df, output_dir)
    fig02_per_function_cache_hit_rate(blind_fn_df, aware_fn_df, output_dir)
    fig03_cache_aware_candidate_score_heatmap(candidate_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
