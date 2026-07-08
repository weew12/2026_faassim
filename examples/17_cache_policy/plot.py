"""
文件作用：cache_policy 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_policy_hit_rate_comparison.png/pdf：
  三个策略的 hit_rate 柱状图（fifo / lru / utility_aware）。
  论文 demo 关键图 —— 视觉证明 utility_aware 是 fifo 的 2.5x。
- fig02_per_function_hit_rate.png/pdf：
  per-(policy, function) hit_rate 分组柱状图。
  显示每个函数在每个策略下的命中率（img-resize 是最大受益函数）。
- fig03_cache_state_evolution.png/pdf：
  三个策略的 cache_used 随 request_id 变化的三栏小图，叠加 capacity=4 参考线。
  论文 demo 关键诚实性图 —— 展示各策略缓存使用模式的差异。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：17_cache_policy/outputs/ 目录下的 CSV
输出：17_cache_policy/figures/ 目录下的 png + pdf

运行：
    python -u examples/17_cache_policy/plot.py
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
    "fifo": "#d62728",
    "lru": "#ff7f0e",
    "utility_aware": "#2ca02c",
}
POLICY_ORDER = ["fifo", "lru", "utility_aware"]


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "utility_aware": "utility",
        "total_cold_start_penalty": "cold_penalty",
        "cold_start_penalty_reduction": "cold_reduction",
        "hit_rate_improvement": "hit_improve",
        "hit_rate_ratio": "hit_ratio",
        "latency_reduction": "lat_reduction",
        "avg_cache_used_after": "avg_cache_used",
        "best_function_hit_rate": "best_fn_hit",
        "video-transcode": "video",
        "img-resize": "img",
        "json-parse": "json",
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
        description="Generate paper-demo figures for 17_cache_policy.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/17_cache_policy/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/17_cache_policy/figures.",
    )
    return parser.parse_args()


def fig01_policy_hit_rate_comparison(policy_summary_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    三个策略的 hit_rate 柱状图（论文 demo 关键图）。

    utility_aware 是 fifo 的 2.5x。
    """
    if policy_summary_df.empty or "policy_name" not in policy_summary_df.columns:
        logger.warning("policy_summary is empty; skip fig01")
        return None

    df = policy_summary_df.copy()
    df["__order__"] = df["policy_name"].apply(
        lambda p: POLICY_ORDER.index(p) if p in POLICY_ORDER else len(POLICY_ORDER)
    )
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    colors = [POLICY_COLORS.get(p, "#7f7f7f") for p in df["policy_name"]]
    bars = ax.bar(
        df["policy_name"],
        df["hit_rate"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, df["hit_rate"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.4f}",
            ha="center",
            va="bottom",
        )
    # 标 utility_aware 是 fifo 的 2.5x
    fifo_row = df[df["policy_name"] == "fifo"]
    if not fifo_row.empty:
        base_hit = float(fifo_row["hit_rate"].iloc[0])
        u_row = df[df["policy_name"] == "utility_aware"]
        if not u_row.empty and base_hit > 0:
            u_hit = float(u_row["hit_rate"].iloc[0])
            ratio = u_hit / base_hit
            ax.set_title(f"Cache policy hit rate (utility_aware = {ratio:.2f}x fifo)")

    ax.set_ylabel("hit_rate")
    ax.set_ylim(0, max(0.5, df["hit_rate"].max() * 1.2))
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_policy_hit_rate_comparison"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_function_hit_rate(function_summary_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    per-(policy, function) hit_rate 分组柱状图。

    显示每个函数在每个策略下的命中率。
    """
    if function_summary_df.empty or "function_name" not in function_summary_df.columns:
        logger.warning("function_summary is empty; skip fig02")
        return None

    df = function_summary_df.copy()
    function_order_df = (
        df.groupby("function_name", as_index=False)["request_count"]
        .max()
        .sort_values(["request_count", "function_name"], ascending=[False, True])
    )
    functions = function_order_df["function_name"].tolist()
    if not functions:
        return None

    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    x = np.arange(len(functions))
    width = 0.25

    for i, policy in enumerate(POLICY_ORDER):
        sub = df[df["policy_name"] == policy].set_index("function_name")
        vals = [float(sub.loc[f, "hit_rate"]) if f in sub.index else 0.0 for f in functions]
        bars = ax.bar(
            x + (i - 1) * width,
            vals,
            width,
            label=policy,
            color=POLICY_COLORS.get(policy, "#7f7f7f"),
            edgecolor="black",
            linewidth=0.5,
        )
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{v:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(functions, rotation=15)
    ax.set_title("Per-function hit_rate by policy")
    ax.set_xlabel("function_name")
    ax.set_ylabel("hit_rate")
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_per_function_hit_rate"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cache_state_evolution(state_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    三个策略的 cache_used 随 request_id 变化的三栏小图，叠加 capacity 参考线。
    """
    if state_df.empty or "cache_used" not in state_df.columns:
        logger.warning("state df is empty; skip fig03")
        return None

    df = state_df.copy()
    if "cache_capacity" not in df.columns:
        df["cache_capacity"] = 4

    capacity_value = int(df["cache_capacity"].iloc[0]) if len(df) > 0 else 4
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True, constrained_layout=True)
    for ax, policy in zip(axes, POLICY_ORDER):
        sub = df[df["policy_name"] == policy].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("request_id")
        ax.plot(
            sub["request_id"],
            sub["cache_used"],
            linewidth=2.0,
            color=POLICY_COLORS.get(policy, "#7f7f7f"),
            label=policy,
            marker="o",
            markersize=4,
        )
        ax.axhline(
            capacity_value,
            color="black",
            linestyle="--",
            linewidth=1.0,
            alpha=0.6,
            label=f"capacity = {capacity_value}",
        )
        ax.set_title(policy)
        ax.set_xlabel("request_id")
        ax.set_ylim(0, capacity_value + 1)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="lower right", fontsize=8)
    axes[0].set_ylabel("cache_used (memory_units)")
    fig.suptitle("Cache state evolution (cache_used over request_id)", fontsize=14)

    out = out_dir / "fig03_cache_state_evolution"
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
        | df["metric"].str.startswith("miss_count__")
        | df["metric"].isin(["policy_summary_count"])
    )
    performance_mask = (
        df["metric"].str.startswith("hit_rate__")
        | df["metric"].str.startswith("avg_latency__")
        | df["metric"].str.startswith("avg_cache_used_after__")
        | df["metric"].str.startswith("best_function_hit_rate__")
    )

    panels = [
        (df[count_mask], "Counts and totals", "#4c78a8"),
        (df[performance_mask], "Policy performance", "#59a14f"),
        (df[~(count_mask | performance_mask)], "Relative improvements", "#f58518"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(21, 8), constrained_layout=True)
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

    fig.suptitle("Cache Policy Paper Highlight Metrics", fontsize=14)

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

    policy_summary_df = pd.read_csv(input_dir / "cache_policy_summary.csv", encoding="utf-8-sig")
    function_summary_df = pd.read_csv(input_dir / "cache_function_summary.csv", encoding="utf-8-sig")
    state_df = pd.read_csv(input_dir / "cache_state.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "cache_policy_paper_highlight.csv", encoding="utf-8-sig")

    fig01_policy_hit_rate_comparison(policy_summary_df, output_dir)
    fig02_per_function_hit_rate(function_summary_df, output_dir)
    fig03_cache_state_evolution(state_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
