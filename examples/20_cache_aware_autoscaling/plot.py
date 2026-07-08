"""
文件作用：cache_aware_autoscaling 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_r_cache_vs_load_timeseries.png/pdf（论文 demo 关键图）：
  5 个时间点上 total_r_cache / total_r_load / total_r_desired 折线。
  论文 demo 关键图 —— 视觉证明 R_load 主导在 time=1/2 的扩容。
- fig02_action_distribution.png/pdf（论文 demo 关键图）：
  5 类 (action, reason) 的 events 横向条形。
  论文 demo 关键图 —— 展示决策分布（scale_out=5, scale_in=6, protect=8, prewarm=0, observe=1）。
- fig03_per_function_delta_heatmap.png/pdf（论文 demo 关键图）：
  4 函数 × 5 time 的 delta 热力图（正=绿 scale_out，0=灰 protect/observe，负=红 scale_in）。
  论文 demo 关键图 —— 展示每个函数每个时间点的扩缩方向。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：20_cache_aware_autoscaling/outputs/ 目录下的 CSV
输出：20_cache_aware_autoscaling/figures/ 目录下的 png + pdf

运行：
    python -u examples/20_cache_aware_autoscaling/plot.py
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


ACTION_COLORS = {
    "scale_out": "#2ca02c",
    "protect": "#1f77b4",
    "observe": "#7f7f7f",
    "scale_in": "#d62728",
    "prewarm": "#ff7f0e",
}
ACTION_ORDER = ["scale_out", "protect", "prewarm", "observe", "scale_in"]


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "action_count": "action",
        "r_load_dominant": "load_dominant",
        "r_cache_only": "cache_only",
        "r_both_active": "both_active",
        "r_neither_active": "neither_active",
        "cache_budget": "budget",
        "decision_plan": "plan",
        "per_time_total": "t_total",
        "r_desired": "desired",
        "scale_out": "out",
        "scale_in": "in",
    }
    label = str(metric)
    for old, new in replacements.items():
        label = label.replace(old, new)
    label = label.replace("__", " / ")
    return label.replace(".0", "")


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
        description="Generate paper-demo figures for 20_cache_aware_autoscaling.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/20_cache_aware_autoscaling/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/20_cache_aware_autoscaling/figures.",
    )
    return parser.parse_args()


def fig01_r_cache_vs_load_timeseries(
    time_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    5 个时间点上 total_r_cache / total_r_load / total_r_desired 折线（论文 demo 关键图）。
    """
    if time_summary_df.empty:
        logger.warning("time_summary_df is empty; skip fig01")
        return None

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    ax.plot(
        time_summary_df["time"],
        time_summary_df["total_r_cache"],
        "o-",
        label="total_r_cache",
        color="steelblue",
        linewidth=2,
        markersize=8,
    )
    ax.plot(
        time_summary_df["time"],
        time_summary_df["total_r_load"],
        "s-",
        label="total_r_load",
        color="darkorange",
        linewidth=2,
        markersize=8,
    )
    ax.plot(
        time_summary_df["time"],
        time_summary_df["total_r_desired"],
        "^--",
        label="total_r_desired = max(R_cache, R_load)",
        color="gray",
        linewidth=1.5,
        markersize=8,
        alpha=0.7,
    )

    # 在每个 time 点标 R_desired 数字
    for _, row in time_summary_df.iterrows():
        ax.text(
            row["time"],
            row["total_r_desired"] + 0.3,
            f"{int(row['total_r_desired'])}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="gray",
        )

    ax.set_xlabel("time (sampling round)")
    ax.set_ylabel("total replicas across 4 functions")
    ax.set_xticks(time_summary_df["time"])
    ax.set_title("Cache-aware autoscaling: R_cache vs R_load (time series)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(time_summary_df["total_r_desired"]) + 2)

    out = out_dir / "fig01_r_cache_vs_load_timeseries"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_action_distribution(
    action_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    5 类 (action, reason) 的 events 横向条形（论文 demo 关键图）。
    """
    if action_summary_df.empty:
        logger.warning("action_summary_df is empty; skip fig02")
        return None

    df = action_summary_df.copy()
    # 构造 label
    df["label"] = df["action"] + " (" + df["reason"] + ")"
    df = df.sort_values(["action", "events"], ascending=[True, True]).reset_index(drop=True)
    # 颜色按 action 类型
    colors = [ACTION_COLORS.get(a, "#7f7f7f") for a in df["action"]]

    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
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
    ax.set_title("Action distribution (action + reason)")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig02_action_distribution"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_per_function_delta_heatmap(
    decision_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    4 函数 × 5 time 的 delta 热力图（论文 demo 关键图）。
    """
    if decision_df.empty or "delta" not in decision_df.columns:
        logger.warning("decision_df is empty; skip fig03")
        return None

    functions = sorted(decision_df["function_name"].unique())
    times = sorted(decision_df["time"].unique())

    matrix = np.zeros((len(functions), len(times)))
    for i, fn in enumerate(functions):
        for j, t in enumerate(times):
            row = decision_df[
                (decision_df["function_name"] == fn) & (decision_df["time"] == t)
            ]
            v = int(row["delta"].iloc[0]) if not row.empty else 0
            matrix[i, j] = v

    # 用 RdYlGn 发散色板（负=红，0=黄，正=绿）
    vmax = max(abs(matrix.min()), abs(matrix.max()), 1)
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    im = ax.imshow(
        matrix,
        cmap="RdYlGn",
        aspect="auto",
        vmin=-vmax,
        vmax=vmax,
    )

    for i in range(len(functions)):
        for j in range(len(times)):
            v = int(matrix[i, j])
            color = "white" if abs(v) > vmax * 0.5 else "black"
            ax.text(
                j,
                i,
                f"{v:+d}",
                ha="center",
                va="center",
                color=color,
                fontsize=10,
            )

    ax.set_xticks(np.arange(len(times)))
    ax.set_yticks(np.arange(len(functions)))
    ax.set_xticklabels([f"t={int(t)}" for t in times])
    ax.set_yticklabels(functions)
    ax.set_xlabel("time")
    ax.set_ylabel("function_name")
    ax.set_title("Per-function delta = R_desired - current_replicas (+: scale_out, -: scale_in)")
    fig.colorbar(im, ax=ax, label="delta (replicas)")

    out = out_dir / "fig03_per_function_delta_heatmap"
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

    action_mask = df["metric"].str.startswith("action_count__")
    budget_mask = (
        df["metric"].str.startswith("cache_budget")
        | df["metric"].str.startswith("r_cache_rejected")
        | df["metric"].str.startswith("decision_plan")
    )
    time_mask = df["metric"].str.startswith("per_time_total_")
    r_mix_mask = ~(action_mask | budget_mask | time_mask)

    panels = [
        (df[action_mask], "Action counts", "#4c78a8"),
        (df[r_mix_mask], "R-cache / R-load mix", "#59a14f"),
        (df[budget_mask], "Budget and plan checks", "#f58518"),
        (df[time_mask], "Per-time totals", "#9c755f"),
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

    fig.suptitle("Cache-aware Autoscaling Paper Highlight Metrics", fontsize=14)

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

    decision_df = pd.read_csv(
        input_dir / "cache_aware_autoscaling_decision.csv", encoding="utf-8-sig",
    )
    time_summary_df = pd.read_csv(
        input_dir / "cache_aware_autoscaling_time_summary.csv", encoding="utf-8-sig",
    )
    action_summary_df = pd.read_csv(
        input_dir / "cache_aware_autoscaling_action_summary.csv", encoding="utf-8-sig",
    )
    paper_df = pd.read_csv(
        input_dir / "cache_aware_autoscaling_paper_highlight.csv", encoding="utf-8-sig",
    )

    fig01_r_cache_vs_load_timeseries(time_summary_df, output_dir)
    fig02_action_distribution(action_summary_df, output_dir)
    fig03_per_function_delta_heatmap(decision_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
