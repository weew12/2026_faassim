"""
文件作用：batch_experiment 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_policy_high_capacity_hit_ratio.png/pdf：
  default_skippy vs fixed_node 选到 high-capacity 节点（server_1）的命中率柱状图。
  论文 demo 关键图 —— 视觉证明 default_skippy 100% 选高 capacity 节点，
  fixed_node 100% 选 server_0。
- fig02_per_case_avg_probe_duration.png/pdf：
  8 个 case 的 avg_probe_duration 散点（按 case_id 排序），颜色按 policy、
  形状按 workload。显示 capacity 不同的两种 policy 在 sim 模型下 probe duration
  几乎一致（论文里要诚实写出来的 sim 模型特性）。
- fig03_scheduled_node_distribution.png/pdf：
  每个 case 的 scheduled_node 分布柱状图（4 workload × 2 policy）。
  显示 default_skippy 全部选 server_1，fixed_node 全部选 server_0。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图。

输入：14_batch_experiment/outputs/ 目录下的 CSV
输出：14_batch_experiment/figures/ 目录下的 png + pdf

运行：
    python -u examples/14_batch_experiment/plot.py
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

NODE_COLORS = {
    "server_0": "#d62728",
    "server_1": "#2ca02c",
    "server_2": "#1f77b4",
    "server_3": "#ff7f0e",
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
        description="Generate paper-demo figures for 14_batch_experiment.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/14_batch_experiment/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/14_batch_experiment/figures.",
    )
    return parser.parse_args()


def fig01_policy_high_capacity_hit_ratio(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    策略 high_capacity_hit_ratio 柱状图。

    论文 demo 关键图：default_skippy 100% 选高 capacity 节点，fixed_node 100% 选 server_0。
    """
    if paper_df.empty or "metric" not in paper_df.columns or "value" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig01")
        return None

    df = paper_df[paper_df["metric"].str.startswith("high_capacity_hit_ratio__")].copy()
    if df.empty:
        logger.warning("no high_capacity_hit_ratio rows; skip fig01")
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

    out = out_dir / "fig01_policy_high_capacity_hit_ratio"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_case_avg_probe_duration(batch_results_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    8 个 case 的 avg_probe_duration 散点（按 case_id 排序），颜色按 policy、形状按 workload。

    论文 demo 关键诚实性图：capacity 不同的两种 policy 在 sim 模型下 probe duration
    几乎一致（因为 sim 的 t_exec 等于 base_duration，capacity 不改 single-invoke duration）。
    """
    if batch_results_df.empty or "case_id" not in batch_results_df.columns:
        logger.warning("batch_results is empty; skip fig02")
        return None

    df = batch_results_df.copy()
    if "avg_probe_duration" not in df.columns:
        logger.warning("no avg_probe_duration column; skip fig02")
        return None
    df["avg_probe_duration"] = pd.to_numeric(df["avg_probe_duration"], errors="coerce")
    df = df.sort_values("case_id").reset_index(drop=True)

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
                sub["avg_probe_duration"],
                s=130,
                color=POLICY_COLORS.get(policy, "#7f7f7f"),
                edgecolors="black",
                linewidths=0.6,
                marker=marker,
                label=label,
                zorder=3,
            )

    ax.set_title("Per-case avg_probe_duration (capacity ≠ duration, sim honest fact)")
    compact_labels = [
        f"{row.policy.replace('default_skippy', 'default').replace('fixed_node', 'fixed')}\n"
        f"{row.workload.replace('_load', '')}/s{row.seed}"
        for _, row in df.iterrows()
    ]
    ax.set_xlabel("case")
    ax.set_ylabel("avg_probe_duration (s)")
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

    out = out_dir / "fig02_per_case_avg_probe_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_scheduled_node_distribution(batch_results_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每个 case 的 scheduled_node 分布柱状图（4 workload × 2 policy）。

    显示 default_skippy 全部选 server_1，fixed_node 全部选 server_0。
    """
    if batch_results_df.empty or "scheduled_node" not in batch_results_df.columns:
        logger.warning("batch_results has no scheduled_node; skip fig03")
        return None

    df = batch_results_df.copy()
    if "policy" not in df.columns or "workload" not in df.columns:
        logger.warning("batch_results missing policy/workload; skip fig03")
        return None

    pivot = df.pivot_table(
        index="workload", columns="policy", values="scheduled_node",
        aggfunc=lambda x: ",".join(sorted(set(x.dropna().astype(str)))),
    )
    pivot.columns.name = None

    # 第二个子图：每个 case 选中的节点（用颜色块）
    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)

    # 网格：x=case_idx, y=0 (1 row)，颜色按 scheduled_node
    policy_order = {p: i for i, p in enumerate(POLICY_ORDER)}
    df["__policy_order__"] = df["policy"].map(policy_order).fillna(len(POLICY_ORDER))
    df_sorted = df.sort_values(["__policy_order__", "workload", "seed"]).reset_index(drop=True)
    x = np.arange(len(df_sorted))
    colors = [NODE_COLORS.get(n, "#7f7f7f") for n in df_sorted["scheduled_node"]]
    ax.bar(x, [1.0] * len(df_sorted), color=colors, edgecolor="black", linewidth=0.5)

    # 标 case_id 在 x 轴下方
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{r.policy[:3]}/{r.workload[:3]}/s{r.seed}" for _, r in df_sorted.iterrows()],
        rotation=20,
        fontsize=8,
    )
    ax.set_yticks([])
    ax.set_ylim(0, 1.1)
    ax.set_title("Per-case scheduled_node (default_skippy → server_1, fixed_node → server_0)")

    # legend
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor="black", label=n)
        for n, c in NODE_COLORS.items()
        if n in df_sorted["scheduled_node"].unique()
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=8, ncol=4)
    ax.grid(True, axis="x", alpha=0.2)

    out = out_dir / "fig03_scheduled_node_distribution"
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

    df = df.sort_values("value_num", ascending=True)

    count_metrics = {
        "total_cases",
        "total_policies",
        "total_workloads",
        "total_seeds",
        "total_invocations",
        "avg_invocations_per_case",
    }
    count_df = df[df["metric"].isin(count_metrics)].sort_values("value_num", ascending=True)
    detail_df = df[~df["metric"].isin(count_metrics)].sort_values("value_num", ascending=True)

    def short_metric_label(metric: str) -> str:
        label = (
            metric.replace("default_skippy", "default")
            .replace("fixed_node", "fixed")
            .replace("high_capacity_hit_ratio", "high_cap_hit")
            .replace("avg_probe_seconds", "avg_probe_s")
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
        figsize=(14, 6.5),
        constrained_layout=True,
    )
    draw_barh(ax_counts, count_df, "Batch Size Metrics", "#4c78a8")
    draw_barh(ax_details, detail_df, "Policy / Duration Metrics", "#f58518")
    fig.suptitle("Batch Experiment Paper Highlight Metrics", fontsize=12)

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

    batch_results_df = pd.read_csv(input_dir / "batch_results.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "batch_paper_highlight.csv", encoding="utf-8-sig")

    fig01_policy_high_capacity_hit_ratio(paper_df, output_dir)
    fig02_per_case_avg_probe_duration(batch_results_df, output_dir)
    fig03_scheduled_node_distribution(batch_results_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
