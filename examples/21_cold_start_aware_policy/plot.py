"""
文件作用：cold_start_aware_policy 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_policy_comparison_metrics.png/pdf（论文 demo 关键图）：
  3 个核心 metric (hit_rate / avg_latency / total_cold_start_penalty)
  × 2 个 policy (cold_start_aware / fixed_keep_alive) 的分组柱状图。
- fig02_per_function_hit_rate.png/pdf（论文 demo 关键图）：
  6 函数 × 2 policy 的 hit_rate 分组柱状图。
  论文 demo 关键图 —— 展示 img-resize (高频) 在 cold_start_aware 命中率从 0.44 → 0.78。
- fig03_decision_distribution.png/pdf：
  4 类 (policy, decision, reason) 的 events 横向条形。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：21_cold_start_aware_policy/outputs/ 目录下的 CSV
输出：21_cold_start_aware_policy/figures/ 目录下的 png + pdf

运行：
    python -u examples/21_cold_start_aware_policy/plot.py
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
    "cold_start_aware": "#2ca02c",
    "fixed_keep_alive": "#7f7f7f",
}


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "cold_start_aware": "aware",
        "fixed_keep_alive": "fixed",
        "total_cold_start_penalty": "cold_penalty",
        "avg_keep_alive_window": "avg_window",
        "hit_rate_improvement": "hit_improve",
        "hit_rate_ratio": "hit_ratio",
        "latency_reduction": "latency_reduce",
        "cold_start_penalty_reduction": "cold_reduce",
        "avg_keep_alive_window_diff": "window_diff",
        "request_decision": "req_decision",
        "eviction_state": "evict_state",
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
        description="Generate paper-demo figures for 21_cold_start_aware_policy.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/21_cold_start_aware_policy/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/21_cold_start_aware_policy/figures.",
    )
    return parser.parse_args()


def fig01_policy_comparison_metrics(
    policy_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 个核心 metric × 2 个 policy 的分组柱状图（论文 demo 关键图）。
    """
    if policy_summary_df.empty:
        logger.warning("policy_summary_df is empty; skip fig01")
        return None

    metrics = [
        ("hit_rate", "hit_rate"),
        ("avg_latency", "avg_latency (s)"),
        ("total_cold_start_penalty", "total_cold_start_penalty (s)"),
    ]
    policies = ["fixed_keep_alive", "cold_start_aware"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), constrained_layout=True)

    for ax, (col, label) in zip(axes, metrics):
        values = []
        for p in policies:
            row = policy_summary_df[policy_summary_df["policy_name"] == p]
            v = float(row[col].iloc[0]) if (not row.empty and col in row.columns) else 0.0
            values.append(v)

        bars = ax.bar(
            policies,
            values,
            color=[POLICY_COLORS[p] for p in policies],
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
        ax.tick_params(axis="x", rotation=10)
        ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        "Cold-start-aware vs fixed keep-alive policy (3 key metrics)",
        fontsize=12,
        fontweight="bold",
    )
    out = out_dir / "fig01_policy_comparison_metrics"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_function_hit_rate(
    function_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    6 函数 × 2 policy 的 hit_rate 分组柱状图（论文 demo 关键图）。
    """
    if function_summary_df.empty:
        logger.warning("function_summary_df is empty; skip fig02")
        return None

    all_fns = sorted(function_summary_df["function_name"].unique())
    policies = ["fixed_keep_alive", "cold_start_aware"]

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)

    x = np.arange(len(all_fns))
    width = 0.35

    for i, p in enumerate(policies):
        sub = function_summary_df[function_summary_df["policy_name"] == p]
        sub = sub.set_index("function_name").reindex(all_fns).reset_index()
        values = [float(v) if pd.notna(v) else 0.0 for v in sub["hit_rate"]]
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
    ax.set_ylabel("hit_rate (0-1)")
    ax.set_xlabel("function_name")
    ax.set_ylim(0, 1.0)
    ax.set_title("Per-function hit rate: cold_start_aware vs fixed_keep_alive")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_per_function_hit_rate"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_decision_distribution(
    decision_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    4 类 (policy, decision, reason) 的 events 横向条形。
    """
    if decision_summary_df.empty:
        logger.warning("decision_summary_df is empty; skip fig03")
        return None

    df = decision_summary_df.copy()
    df["label"] = df["policy_name"] + " | " + df["decision"] + " (" + df["reason"] + ")"
    df = df.sort_values(["policy_name", "events"], ascending=[True, True]).reset_index(drop=True)
    colors = [POLICY_COLORS.get(p, "#7f7f7f") for p in df["policy_name"]]

    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    bars = ax.barh(df["label"], df["events"], color=colors, edgecolor="black", linewidth=0.5)
    for bar, v in zip(bars, df["events"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{int(v)}",
            ha="left",
            va="center",
        )
    ax.set_xlabel("events count")
    ax.set_title("Decision distribution (policy | decision + reason)")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig03_decision_distribution"
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
        df["metric"].str.startswith("hit_rate__")
        | df["metric"].str.startswith("avg_latency__")
        | df["metric"].str.startswith("total_cold_start_penalty__")
        | df["metric"].str.startswith("avg_keep_alive_window__")
        | df["metric"].str.startswith("eviction_count__")
    )
    improvement_mask = (
        df["metric"].str.startswith("hit_rate_improvement__")
        | df["metric"].str.startswith("hit_rate_ratio__")
        | df["metric"].str.startswith("latency_reduction__")
        | df["metric"].str.startswith("cold_start_penalty_reduction__")
        | df["metric"].str.startswith("avg_keep_alive_window_diff__")
    )
    request_join_mask = df["metric"].str.startswith("request_decision")
    eviction_join_mask = df["metric"].str.startswith("eviction_state")

    panels = [
        (df[per_policy_mask], "Per-policy metrics", "#4c78a8"),
        (df[improvement_mask], "Aware over fixed", "#59a14f"),
        (df[request_join_mask], "Request-decision join", "#f58518"),
        (df[eviction_join_mask], "Eviction-state join", "#9c755f"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(18, 11), constrained_layout=True)
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

    fig.suptitle("Cold-start-aware Policy Paper Highlight Metrics", fontsize=14)

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
        input_dir / "cold_start_policy_summary.csv", encoding="utf-8-sig",
    )
    function_summary_df = pd.read_csv(
        input_dir / "cold_start_function_summary.csv", encoding="utf-8-sig",
    )
    decision_summary_df = pd.read_csv(
        input_dir / "cold_start_decision_summary.csv", encoding="utf-8-sig",
    )
    paper_df = pd.read_csv(
        input_dir / "cold_start_policy_paper_highlight.csv", encoding="utf-8-sig",
    )

    fig01_policy_comparison_metrics(policy_summary_df, output_dir)
    fig02_per_function_hit_rate(function_summary_df, output_dir)
    fig03_decision_distribution(decision_summary_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
