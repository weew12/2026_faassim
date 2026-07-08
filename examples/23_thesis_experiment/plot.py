"""
文件作用：thesis_experiment 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_three_cache_dim_hit_rates.png/pdf（论文 demo 关键图）：
  3 个缓存维度 (warm / image / data) × 3 个 case (LoadOnly / FaasCache / CacheAwareJoint) 的分组柱状图。
  论文 demo 关键图 —— 展示 CacheAwareJoint 在 3 个维度上全面胜出。
- fig02_latency_by_case.png/pdf（论文 demo 关键图）：
  3 case 的 avg_latency + p95_latency 双柱对比。
- fig03_r_cache_vs_r_load_by_case.png/pdf（论文 demo 关键图）：
  3 case 的 avg_r_cache / avg_r_load / avg_r_desired 三柱对比（验证 R_desired = max 公式生效）。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：23_thesis_experiment/outputs/ 目录下的 CSV
输出：23_thesis_experiment/figures/ 目录下的 png + pdf

运行：
    python -u examples/23_thesis_experiment/plot.py
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


CASE_COLORS = {
    "load_only": "#d62728",
    "faascache": "#ff7f0e",
    "cache_aware_joint": "#2ca02c",
}
CASE_ORDER = ["load_only", "faascache", "cache_aware_joint"]


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "cache_aware_joint": "joint",
        "load_only": "load",
        "faascache": "faas",
        "warm_hit_rate": "warm_hit",
        "image_cache_hit_rate": "image_hit",
        "data_cache_hit_rate": "data_hit",
        "total_cold_start_penalty": "cold_penalty",
        "avg_latency_reduction": "latency_reduce",
        "cold_start_penalty_reduction": "cold_reduce",
        "image_cache_hit_rate_improvement": "image_improve",
        "data_cache_hit_rate_improvement": "data_improve",
        "r_dominant": "r_dom",
        "result_candidate": "result_candidate",
        "request_decision": "request_decision",
        "_vs_": " / ",
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
        description="Generate paper-demo figures for 23_thesis_experiment.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/23_thesis_experiment/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/23_thesis_experiment/figures.",
    )
    return parser.parse_args()


def fig01_three_cache_dim_hit_rates(
    policy_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 个缓存维度 × 3 个 case 的分组柱状图（论文 demo 关键图）。
    """
    if policy_summary_df.empty:
        logger.warning("policy_summary_df is empty; skip fig01")
        return None

    metrics = [
        ("warm_hit_rate", "warm"),
        ("image_cache_hit_rate", "image"),
        ("data_cache_hit_rate", "data"),
    ]
    cases = [c for c in CASE_ORDER if c in set(policy_summary_df["case_id"])]

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)

    x = np.arange(len(metrics))
    width = 0.25

    for i, c in enumerate(cases):
        sub = policy_summary_df[policy_summary_df["case_id"] == c]
        values = [float(sub[m].iloc[0]) if not sub.empty else 0.0 for m, _ in metrics]
        bars = ax.bar(
            x + (i - 1) * width,
            values,
            width,
            color=CASE_COLORS[c],
            edgecolor="black",
            linewidth=0.5,
            label=c,
        )
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in metrics])
    ax.set_ylabel("hit_rate")
    ax.set_ylim(0, 1.15)
    ax.set_title("Thesis: three cache dimension hit rates by case")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_three_cache_dim_hit_rates"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_latency_by_case(
    policy_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 case 的 avg_latency + p95_latency 双柱对比（论文 demo 关键图）。
    """
    if policy_summary_df.empty:
        logger.warning("policy_summary_df is empty; skip fig02")
        return None

    cases = [c for c in CASE_ORDER if c in set(policy_summary_df["case_id"])]

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)

    x = np.arange(len(cases))
    width = 0.35

    avg_lat = []
    p95_lat = []
    for c in cases:
        sub = policy_summary_df[policy_summary_df["case_id"] == c]
        avg_lat.append(float(sub["avg_latency"].iloc[0]) if not sub.empty else 0.0)
        p95_lat.append(float(sub["p95_latency"].iloc[0]) if not sub.empty else 0.0)

    bars1 = ax.bar(
        x - width / 2,
        avg_lat,
        width,
        color="steelblue",
        edgecolor="black",
        linewidth=0.5,
        label="avg_latency (s)",
    )
    bars2 = ax.bar(
        x + width / 2,
        p95_lat,
        width,
        color="darkorange",
        edgecolor="black",
        linewidth=0.5,
        label="p95_latency (s)",
    )
    for bar, v in zip(bars1, avg_lat):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    for bar, v in zip(bars2, p95_lat):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(cases, rotation=10, ha="right")
    ax.set_ylabel("latency (s)")
    ax.set_xlabel("case_id")
    ax.set_title("Per-case latency: avg vs p95")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_latency_by_case"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_r_cache_vs_r_load_by_case(
    policy_summary_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    3 case 的 R_cache / R_load / R_desired 三柱对比（论文 demo 关键图）。

    验证 R_desired = max(R_cache, R_load) 公式生效：
    - LoadOnly: R_cache=0, R_load=1, R_desired=1
    - FaasCache: R_cache=0.97, R_load=0, R_desired=0.97
    - CacheAwareJoint: R_cache=0.97, R_load=1, R_desired=1
    """
    if policy_summary_df.empty:
        logger.warning("policy_summary_df is empty; skip fig03")
        return None

    cases = [c for c in CASE_ORDER if c in set(policy_summary_df["case_id"])]

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)

    x = np.arange(len(cases))
    width = 0.25

    r_cache = []
    r_load = []
    r_desired = []
    for c in cases:
        sub = policy_summary_df[policy_summary_df["case_id"] == c]
        r_cache.append(float(sub["avg_r_cache"].iloc[0]) if not sub.empty else 0.0)
        r_load.append(float(sub["avg_r_load"].iloc[0]) if not sub.empty else 0.0)
        r_desired.append(float(sub["avg_r_desired"].iloc[0]) if not sub.empty else 0.0)

    bars1 = ax.bar(
        x - width,
        r_cache,
        width,
        color="steelblue",
        edgecolor="black",
        linewidth=0.5,
        label="avg_r_cache",
    )
    bars2 = ax.bar(
        x,
        r_load,
        width,
        color="darkorange",
        edgecolor="black",
        linewidth=0.5,
        label="avg_r_load",
    )
    bars3 = ax.bar(
        x + width,
        r_desired,
        width,
        color="gray",
        edgecolor="black",
        linewidth=0.5,
        label="avg_r_desired = max(R_cache, R_load)",
    )
    for bars, values in [(bars1, r_cache), (bars2, r_load), (bars3, r_desired)]:
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
    ax.set_xticklabels(cases, rotation=10, ha="right")
    ax.set_ylabel("replicas (normalized avg)")
    ax.set_xlabel("case_id")
    ax.set_ylim(0, 1.2)
    ax.set_title("R_cache vs R_load by case (R_desired = max)")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig03_r_cache_vs_r_load_by_case"
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

    per_case_mask = (
        df["metric"].str.startswith("warm_hit_rate__")
        | df["metric"].str.startswith("image_cache_hit_rate__")
        | df["metric"].str.startswith("data_cache_hit_rate__")
        | df["metric"].str.startswith("avg_latency__")
        | df["metric"].str.startswith("p95_latency__")
        | df["metric"].str.startswith("total_cold_start_penalty__")
        | df["metric"].str.startswith("eviction_count__")
    )
    r_mask = (
        df["metric"].str.startswith("avg_r_cache__")
        | df["metric"].str.startswith("avg_r_load__")
        | df["metric"].str.startswith("avg_r_desired__")
        | df["metric"].str.startswith("r_dominant_")
    )
    improvement_mask = (
        df["metric"].str.startswith("avg_latency_reduction__")
        | df["metric"].str.startswith("cold_start_penalty_reduction__")
        | df["metric"].str.startswith("image_cache_hit_rate_improvement__")
        | df["metric"].str.startswith("data_cache_hit_rate_improvement__")
    )
    join_mask = (
        df["metric"].str.startswith("result_candidate")
        | df["metric"].str.startswith("request_decision")
    )

    panels = [
        (df[per_case_mask], "Per-case outcome metrics", "#4c78a8"),
        (df[r_mask], "R-cache / R-load metrics", "#59a14f"),
        (df[improvement_mask], "Joint policy improvements", "#f58518"),
        (df[join_mask], "Join consistency checks", "#9c755f"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(18, 13), constrained_layout=True)
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

    fig.suptitle("Thesis Experiment Paper Highlight Metrics", fontsize=14)

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
        input_dir / "thesis_policy_summary.csv", encoding="utf-8-sig",
    )
    paper_df = pd.read_csv(
        input_dir / "thesis_paper_highlight.csv", encoding="utf-8-sig",
    )

    fig01_three_cache_dim_hit_rates(policy_summary_df, output_dir)
    fig02_latency_by_case(policy_summary_df, output_dir)
    fig03_r_cache_vs_r_load_by_case(policy_summary_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
