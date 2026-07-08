"""
文件作用：edge_cache_scheduler 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_three_cache_dim_hit_rates.png/pdf（论文 demo 关键图）：
  3 个缓存维度 (function / image / data) × 2 个 policy (edge_cache_aware / edge_round_robin) 的分组柱状图。
  论文 demo 关键图 —— 展示 edge_cache_aware 在 3 个维度上全面胜出。
- fig02_per_function_function_cache_hit_rate.png/pdf（论文 demo 关键图）：
  5 函数 × 2 policy 的 function_cache_hit_rate 分组柱状图。
  论文 demo 关键图 —— 展示 edge_cache_aware 把 4 个高频函数命中率从 0-33% 提升到 100%。
- fig03_per_node_selected_count.png/pdf：
  per (policy, node) 的 selected_count 横向条形（论文 demo 关键图 —— 展示 edge_cache_aware 避开 cloud 节点）。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：22_edge_cache_scheduler/outputs/ 目录下的 CSV
输出：22_edge_cache_scheduler/figures/ 目录下的 png + pdf

运行：
    python -u examples/22_edge_cache_scheduler/plot.py
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


POLICY_COLORS = {
    "edge_cache_aware": "#2ca02c",
    "edge_round_robin": "#7f7f7f",
}


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "edge_cache_aware": "aware",
        "edge_round_robin": "rr",
        "function_cache_hit_rate": "function_hit",
        "image_cache_hit_rate": "image_hit",
        "data_cache_hit_rate": "data_hit",
        "avg_estimated_latency": "avg_latency",
        "total_cold_start_penalty": "cold_penalty",
        "total_image_pull_penalty": "image_penalty",
        "total_data_fetch_penalty": "data_penalty",
        "cold_start_penalty_reduction": "cold_reduce",
        "image_pull_penalty_reduction": "image_reduce",
        "data_fetch_penalty_reduction": "data_reduce",
        "avg_estimated_latency_reduction": "latency_reduce",
        "result_candidate": "result_candidate",
        "_improvement": "_improve",
        "_over_": " / ",
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
        description="Generate paper-demo figures for 22_edge_cache_scheduler.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/22_edge_cache_scheduler/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/22_edge_cache_scheduler/figures.",
    )
    return parser.parse_args()


def fig01_three_cache_dim_hit_rates(
    policy_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 个缓存维度 × 2 个 policy 的分组柱状图（论文 demo 关键图）。
    """
    if policy_summary_df.empty:
        logger.warning("policy_summary_df is empty; skip fig01")
        return None

    metrics = [
        ("function_cache_hit_rate", "function"),
        ("image_cache_hit_rate", "image"),
        ("data_cache_hit_rate", "data"),
    ]
    policies = ["edge_round_robin", "edge_cache_aware"]

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)

    x = np.arange(len(metrics))
    width = 0.35

    for i, p in enumerate(policies):
        sub = policy_summary_df[policy_summary_df["policy_name"] == p]
        values = [float(sub[m].iloc[0]) if not sub.empty else 0.0 for m, _ in metrics]
        bars = ax.bar(
            x + (i - 0.5) * width,
            values,
            width,
            color=POLICY_COLORS[p],
            edgecolor="black",
            linewidth=0.5,
            label=p,
        )
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v:.3f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in metrics])
    ax.set_ylabel("hit_rate")
    ax.set_ylim(0, 1.15)
    ax.set_title("Edge cache scheduler: three cache dimension hit rates")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_three_cache_dim_hit_rates"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_function_function_cache_hit_rate(
    function_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    5 函数 × 2 policy 的 function_cache_hit_rate 分组柱状图（论文 demo 关键图）。
    """
    if function_summary_df.empty:
        logger.warning("function_summary_df is empty; skip fig02")
        return None

    all_fns = sorted(function_summary_df["function_name"].unique())
    policies = ["edge_round_robin", "edge_cache_aware"]

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)

    x = np.arange(len(all_fns))
    width = 0.35

    for i, p in enumerate(policies):
        sub = function_summary_df[function_summary_df["policy_name"] == p]
        sub = sub.set_index("function_name").reindex(all_fns).reset_index()
        values = [float(v) if pd.notna(v) else 0.0 for v in sub["function_cache_hit_rate"]]
        bars = ax.bar(
            x + (i - 0.5) * width,
            values,
            width,
            color=POLICY_COLORS[p],
            edgecolor="black",
            linewidth=0.5,
            label=p,
        )
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(all_fns, rotation=15, ha="right")
    ax.set_ylabel("function_cache_hit_rate")
    ax.set_xlabel("function_name")
    ax.set_ylim(0, 1.15)
    ax.set_title("Per-function cache hit rate: edge_cache_aware vs edge_round_robin")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_per_function_function_cache_hit_rate"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_per_node_selected_count(
    node_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    per (policy, node) 的 selected_count 横向条形（论文 demo 关键图）。
    """
    if node_summary_df.empty:
        logger.warning("node_summary_df is empty; skip fig03")
        return None

    df = node_summary_df.copy()
    df["label"] = df["policy_name"] + " | " + df["selected_node"]
    df = df.sort_values(["policy_name", "selected_node"], ascending=[True, True]).reset_index(drop=True)
    colors = [POLICY_COLORS.get(p, "#7f7f7f") for p in df["policy_name"]]

    fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    bars = ax.barh(df["label"], df["request_count"], color=colors, edgecolor="black", linewidth=0.5)
    for bar, v in zip(bars, df["request_count"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{int(v)}",
            ha="left",
            va="center",
        )
    ax.set_xlabel("selected request count")
    ax.set_title("Per-node selected count (policy | node)")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig03_per_node_selected_count"
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

    per_policy_mask = (
        df["metric"].str.startswith("function_cache_hit_rate__")
        | df["metric"].str.startswith("image_cache_hit_rate__")
        | df["metric"].str.startswith("data_cache_hit_rate__")
        | df["metric"].str.startswith("avg_estimated_latency__")
        | df["metric"].str.startswith("total_cold_start_penalty__")
        | df["metric"].str.startswith("total_image_pull_penalty__")
        | df["metric"].str.startswith("total_data_fetch_penalty__")
    )
    hit_improve_mask = (
        df["metric"].str.startswith("function_cache_hit_rate_improvement__")
        | df["metric"].str.startswith("image_cache_hit_rate_improvement__")
        | df["metric"].str.startswith("data_cache_hit_rate_improvement__")
    )
    penalty_reduction_mask = (
        df["metric"].str.startswith("avg_estimated_latency_reduction__")
        | df["metric"].str.startswith("cold_start_penalty_reduction__")
        | df["metric"].str.startswith("image_pull_penalty_reduction__")
        | df["metric"].str.startswith("data_fetch_penalty_reduction__")
    )
    join_mask = df["metric"].str.startswith("result_candidate")

    panels = [
        (df[per_policy_mask], "Per-policy metrics", "#4c78a8"),
        (df[hit_improve_mask], "Hit-rate improvements", "#59a14f"),
        (df[penalty_reduction_mask], "Latency and penalty reductions", "#f58518"),
        (df[join_mask], "Result-candidate join", "#9c755f"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(18, 12), constrained_layout=True)
    axes = axes.ravel()
    for ax, (panel_df, title, color) in zip(axes, panels):
        panel_df = panel_df.sort_values("value_num", ascending=True)
        bars = ax.barh(panel_df["metric"].map(short_metric_label), panel_df["value_num"], color=color)
        max_value = max(float(panel_df["value_num"].max()), 1.0) if not panel_df.empty else 1.0
        label_offset = max_value * 0.005
        for bar, v in zip(bars, panel_df["value_num"]):
            label = f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}"
            ax.text(
                bar.get_width() + label_offset,
                bar.get_y() + bar.get_height() / 2,
                label,
                ha="left",
                va="center",
                fontsize=8,
            )
        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.set_xlim(0, max_value * 1.08)
        ax.grid(True, axis="x", alpha=0.3)
        ax.tick_params(axis="y", labelsize=8)

    fig.suptitle("Edge Cache Scheduler Paper Highlight Metrics", fontsize=14)

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

    policy_summary_df = pd.read_csv(
        input_dir / "edge_cache_policy_summary.csv", encoding="utf-8-sig",
    )
    function_summary_df = pd.read_csv(
        input_dir / "edge_cache_function_summary.csv", encoding="utf-8-sig",
    )
    node_summary_df = pd.read_csv(
        input_dir / "edge_cache_node_summary.csv", encoding="utf-8-sig",
    )
    paper_df = pd.read_csv(
        input_dir / "edge_cache_policy_paper_highlight.csv", encoding="utf-8-sig",
    )

    fig01_three_cache_dim_hit_rates(policy_summary_df, output_dir)
    fig02_per_function_function_cache_hit_rate(function_summary_df, output_dir)
    fig03_per_node_selected_count(node_summary_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
