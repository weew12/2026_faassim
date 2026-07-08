"""
文件作用：experiment_analysis 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_per_run_probe_avg_duration.png/pdf：
  8 个 run 的 probe_avg_duration 散点（按 run_id 排序），颜色按 policy、形状按 workload。
  论文 demo 关键诚实性图 —— capacity 不同的两种 policy 在 sim 模型下 probe duration
  几乎一致。
- fig02_policy_comparison_per_workload.png/pdf：
  按 workload 分组，每个 workload 两条柱 = default_skippy vs fixed_node。
  论文 demo 关键图 —— 视觉证明"两个 workload 下两种 policy 表现一致"。
- fig03_policy_high_capacity_hit_ratio.png/pdf：
  default_skippy vs fixed_node 选到 high-capacity 节点（server_1）的命中率柱状图。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图。

输入：15_experiment_analysis/outputs/ 目录下的 CSV
输出：15_experiment_analysis/figures/ 目录下的 png + pdf

运行：
    python -u examples/15_experiment_analysis/plot.py
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
    "default_skippy": "#2ca02c",
    "fixed_node": "#d62728",
}
POLICY_ORDER = ["default_skippy", "fixed_node"]

WORKLOAD_MARKERS = {
    "low_load": "o",
    "medium_load": "s",
}


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
        description="Generate paper-demo figures for 15_experiment_analysis.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/15_experiment_analysis/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/15_experiment_analysis/figures.",
    )
    return parser.parse_args()


def fig01_per_run_probe_avg_duration(run_metrics_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    per-run probe_avg_duration 散点（8 个 run）。

    颜色按 policy（绿=default_skippy，红=fixed_node），形状按 workload（圆=low，方=medium）。
    """
    if run_metrics_df.empty or "run_id" not in run_metrics_df.columns:
        logger.warning("run_metrics is empty; skip fig01")
        return None

    df = run_metrics_df.copy()
    if "probe_avg_duration" not in df.columns:
        logger.warning("no probe_avg_duration column; skip fig01")
        return None
    df["probe_avg_duration"] = pd.to_numeric(df["probe_avg_duration"], errors="coerce")
    df = df.sort_values("run_id").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)

    for policy in POLICY_ORDER:
        for workload in df["workload"].unique() if "workload" in df.columns else [None]:
            sub = df[(df.get("policy") == policy) & (df.get("workload") == workload)]
            if sub.empty:
                continue
            marker = WORKLOAD_MARKERS.get(workload, "o")
            label = f"{policy}/{workload}" if workload else policy
            ax.scatter(
                sub.index,
                sub["probe_avg_duration"],
                s=130,
                color=POLICY_COLORS.get(policy, "#7f7f7f"),
                edgecolors="black",
                linewidths=0.6,
                marker=marker,
                label=label,
                zorder=3,
            )

    ax.set_title("Per-run probe_avg_duration (capacity != duration, sim honest fact)")
    compact_labels = [
        f"{row.policy.replace('default_skippy', 'default').replace('fixed_node', 'fixed')}\n"
        f"{row.workload.replace('_load', '')}/s{row.seed}"
        for _, row in df.iterrows()
    ]
    ax.set_xlabel("run")
    ax.set_ylabel("probe_avg_duration (s)")
    ax.set_xticks(df.index)
    ax.set_xticklabels(compact_labels, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        fontsize=8,
        ncol=4,
        framealpha=0.9,
    )

    out = out_dir / "fig01_per_run_probe_avg_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_policy_comparison_per_workload(summary_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    按 workload 分组，每个 workload 两条柱 = default_skippy vs fixed_node。
    """
    if summary_df.empty or "policy" not in summary_df.columns or "workload" not in summary_df.columns:
        logger.warning("summary is empty; skip fig02")
        return None

    df = summary_df.copy()
    if "mean_probe_avg_duration" not in df.columns:
        logger.warning("no mean_probe_avg_duration column; skip fig02")
        return None
    df["mean_probe_avg_duration"] = pd.to_numeric(df["mean_probe_avg_duration"], errors="coerce")

    workloads = sorted(df["workload"].dropna().unique())
    if not workloads:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    x = np.arange(len(workloads))
    width = 0.35

    for i, policy in enumerate(POLICY_ORDER):
        sub = df[df["policy"] == policy].set_index("workload")
        vals = [float(sub.loc[w, "mean_probe_avg_duration"]) if w in sub.index else 0.0 for w in workloads]
        bars = ax.bar(
            x + (i - 0.5) * width,
            vals,
            width,
            label=policy,
            color=POLICY_COLORS.get(policy, "#7f7f7f"),
            edgecolor="black",
            linewidth=0.5,
        )
        for bar, v in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v:.3f}",
                ha="center",
                va="bottom",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(workloads)
    ax.set_title("Policy comparison per workload (mean_probe_avg_duration)")
    ax.set_xlabel("workload")
    ax.set_ylabel("mean_probe_avg_duration (s)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_policy_comparison_per_workload"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_policy_high_capacity_hit_ratio(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    策略 high_capacity_hit_ratio 柱状图。
    """
    if paper_df.empty or "metric" not in paper_df.columns or "value" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig03")
        return None

    df = paper_df[paper_df["metric"].str.startswith("high_capacity_hit_ratio__")].copy()
    if df.empty:
        logger.warning("no high_capacity_hit_ratio rows; skip fig03")
        return None

    df["policy"] = df["metric"].str.replace("high_capacity_hit_ratio__", "", regex=False)
    df["__order__"] = df["policy"].apply(lambda p: POLICY_ORDER.index(p) if p in POLICY_ORDER else len(POLICY_ORDER))
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)
    df["ratio_num"] = pd.to_numeric(df["value"], errors="coerce")

    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    colors = [POLICY_COLORS.get(p, "#7f7f7f") for p in df["policy"]]
    bars = ax.bar(df["policy"], df["ratio_num"], color=colors, edgecolor="black", linewidth=0.5)
    for bar, v in zip(bars, df["ratio_num"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}",
            ha="center",
            va="bottom",
        )
    ax.set_title("Policy high_capacity_node hit ratio (server_1)")
    ax.set_ylabel("hit_ratio")
    ax.set_ylim(0, 1.15)
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig03_policy_high_capacity_hit_ratio"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。
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

    count_metrics = {
        "total_runs",
        "total_policies",
        "total_workloads",
        "total_seeds",
        "total_invocations",
        "total_probes",
        "comparison_row_count",
    }
    count_df = df[df["metric"].isin(count_metrics)].sort_values("value_num", ascending=True)
    detail_df = df[~df["metric"].isin(count_metrics)].sort_values("value_num", ascending=True)

    def short_metric_label(metric: str) -> str:
        label = (
            metric.replace("default_skippy", "default")
            .replace("fixed_node", "fixed")
            .replace("high_capacity_hit_ratio", "high_cap_hit")
            .replace("avg_probe_seconds", "avg_probe_s")
            .replace("speedup_ratio_fixed_over_default_skippy", "speedup_fixed/default")
            .replace("fixed_node_vs_default_skippy", "fixed_vs_default")
            .replace("probe_avg_duration_relative", "probe_avg_rel")
            .replace("medium_load", "medium")
            .replace("low_load", "low")
        )
        return label.replace("__", " / ")

    def draw_barh(ax, sub_df: pd.DataFrame, title: str, color: str) -> None:
        if sub_df.empty:
            ax.set_axis_off()
            return
        labels = [short_metric_label(m) for m in sub_df["metric"]]
        bars = ax.barh(labels, sub_df["value_num"], color=color, edgecolor="black", linewidth=0.4)
        max_v = float(sub_df["value_num"].max()) if not sub_df.empty else 1.0
        offset = max(max_v * 0.015, 0.02)
        for bar, v in zip(bars, sub_df["value_num"]):
            ax.text(
                bar.get_width() + offset,
                bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}",
                ha="left",
                va="center",
                fontsize=8,
            )
        ax.set_title(title)
        ax.set_xlabel("Value")
        ax.set_xlim(0, max_v * 1.25 + offset)
        ax.grid(True, axis="x", alpha=0.3)

    fig, (ax_counts, ax_details) = plt.subplots(
        1, 2,
        figsize=(15, 7),
        constrained_layout=True,
    )
    draw_barh(ax_counts, count_df, "Analysis Count Metrics", "#4c78a8")
    draw_barh(ax_details, detail_df, "Policy / Comparison Metrics", "#f58518")
    fig.suptitle("Experiment Analysis Paper Highlight Metrics", fontsize=12)

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

    run_metrics_df = pd.read_csv(input_dir / "experiment_run_metrics.csv", encoding="utf-8-sig")
    summary_df = pd.read_csv(input_dir / "experiment_summary.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "experiment_paper_highlight.csv", encoding="utf-8-sig")

    fig01_per_run_probe_avg_duration(run_metrics_df, output_dir)
    fig02_policy_comparison_per_workload(summary_df, output_dir)
    fig03_policy_high_capacity_hit_ratio(paper_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
