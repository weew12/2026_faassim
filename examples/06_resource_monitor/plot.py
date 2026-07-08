"""
文件作用：resource_monitor 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_per_invocation_cpu_util.png/pdf：每个 invoke 的 avg/max cpu_util 柱状图
  论文 demo 关键图 —— 直观看 12 次 invoke 各自的资源画像
- fig02_per_replica_util.png/pdf：每个 replica 的 avg/max cpu+mem util
  论文 demo 关键图 —— 直观展示 ResourceMonitor 周期性采集到的资源使用画像
- fig03_cpu_util_timeline.png/pdf：CPU utilization 随时间变化（采样点）
  论文 demo 关键图 —— ResourceMonitor 周期性采样的时序图
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：06_resource_monitor/outputs/ 目录下的 CSV
输出：06_resource_monitor/figures/ 目录下的 png + pdf

运行：
    python -u examples/06_resource_monitor/plot.py
"""

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


def resolve_dirs() -> tuple[Path, Path]:
    """
    解析输入 / 输出目录。
    """
    here = Path(__file__).resolve().parent
    return here / "outputs", here / "figures"


def fig01_per_invocation_cpu_util(join_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：每个 invoke 的 avg/max cpu_util（论文 demo 关键图）。

    ResourceMonitor 是周期采样，单个 invoke 的执行窗口内可能包含 0/1/多个采样点。
    cpu_util 表示该 replica 当前登记的 CPU 占节点容量比例；同一 replica 上多个并发请求会叠加。
    """
    if join_df.empty or "avg_cpu_util" not in join_df.columns:
        logger.warning("join_df is empty; skip fig01")
        return None

    df = join_df.copy().reset_index(drop=True)
    df["invocation_id"] = range(1, len(df) + 1)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(df))
    width = 0.4

    bars_avg = ax.bar(x - width / 2, df["avg_cpu_util"], width,
                      color="#2ca02c", label="avg_cpu_util")
    bars_max = ax.bar(x + width / 2, df["max_cpu_util"], width,
                      color="#d62728", alpha=0.7, label="max_cpu_util")

    for bar, v in zip(bars_avg, df["avg_cpu_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}", ha="center", va="bottom", fontsize=7)
    for bar, v in zip(bars_max, df["max_cpu_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(df["invocation_id"], rotation=0)
    ax.set_xlabel("Invocation ID")
    ax.set_ylabel("CPU utilization (fraction of node capacity)")
    ax.set_title("Per-Invocation CPU Utilization from ResourceMonitor Samples")
    ax.set_ylim(0, max(1.6, df["max_cpu_util"].max() * 1.15))
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_per_invocation_cpu_util"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_replica_util(per_replica_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：每个 replica 的 avg/max cpu+mem util（论文 demo 关键图）。
    """
    if per_replica_df.empty or "avg_cpu_util" not in per_replica_df.columns:
        logger.warning("per_replica_df is empty; skip fig02")
        return None

    df = per_replica_df.copy().reset_index(drop=True)
    # 简化 replica_id 显示（末 4 位）
    df["replica_label"] = df["replica_id"].apply(
        lambda x: f"r{str(x)[-4:]}" if pd.notna(x) else "?"
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    # 左图：cpu_util
    ax = axes[0]
    x = np.arange(len(df))
    width = 0.35
    bars_avg = ax.bar(x - width / 2, df["avg_cpu_util"], width,
                      color="#1f77b4", label="avg_cpu_util")
    bars_max = ax.bar(x + width / 2, df["max_cpu_util"], width,
                      color="#ff7f0e", label="max_cpu_util")
    for bar, v in zip(bars_avg, df["avg_cpu_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    for bar, v in zip(bars_max, df["max_cpu_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["replica_label"], rotation=0)
    ax.set_xlabel("Replica")
    ax.set_ylabel("CPU utilization")
    ax.set_title("Per-Replica CPU Utilization")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    # 右图：mem_util
    ax = axes[1]
    bars_avg = ax.bar(x - width / 2, df["avg_mem_util"], width,
                      color="#2ca02c", label="avg_mem_util")
    bars_max = ax.bar(x + width / 2, df["max_mem_util"], width,
                      color="#d62728", label="max_mem_util")
    for bar, v in zip(bars_avg, df["avg_mem_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.4f}", ha="center", va="bottom", fontsize=8)
    for bar, v in zip(bars_max, df["max_mem_util"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.4f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(df["replica_label"], rotation=0)
    ax.set_xlabel("Replica")
    ax.set_ylabel("Memory utilization")
    ax.set_title("Per-Replica Memory Utilization")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()

    out = out_dir / "fig02_per_replica_util"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cpu_util_timeline(util_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    时序图：CPU utilization 随时间变化（ResourceMonitor 周期性采样）。

    按 replica 区分颜色。优先使用 resource_monitor_sample_probe.csv 中的真实
    ResourceMonitor window.time。
    """
    if util_df.empty or "cpu_util" not in util_df.columns:
        logger.warning("util_df is empty; skip fig03")
        return None

    df = util_df.copy().reset_index(drop=True)
    if "simtime" not in df.columns:
        # 兜底兼容旧输出：没有真实 simtime 时按采样序号重建。
        df = df.sort_values(["replica_id"]).reset_index(drop=True)
        df["simtime"] = (df.groupby("replica_id").cumcount() + 1).astype(float)

    fig, ax = plt.subplots(figsize=(10, 4.5))

    replicas = df["replica_id"].unique().tolist()
    colors = plt.cm.tab10(np.linspace(0, 1, len(replicas)))

    for replica, color in zip(replicas, colors):
        sub = df[df["replica_id"] == replica].sort_values("simtime")
        label = f"replica={str(replica)[-4:]}"
        ax.plot(sub["simtime"], sub["cpu_util"], marker="o", linewidth=1.5,
                markersize=8, color=color, label=label, alpha=0.85)
        for _, row in sub.iterrows():
            ax.annotate(f"{row['cpu_util']:.2f}",
                        xy=(row["simtime"], row["cpu_util"]),
                        xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=7, color=color)

    ax.axhline(y=0.35, color="gray", linestyle="--", linewidth=1.0, alpha=0.6,
               label="one request on replica (0.35)")
    ax.axhline(y=0.70, color="orange", linestyle=":", linewidth=1.0, alpha=0.6,
               label="two concurrent requests on replica (0.70)")
    ax.axhline(y=1.05, color="#d62728", linestyle="-.", linewidth=1.0, alpha=0.6,
               label="three concurrent requests on replica (1.05)")

    ax.set_xlabel("Simtime (s)")
    ax.set_ylabel("CPU utilization")
    ax.set_title("ResourceMonitor CPU Utilization Timeline (per-replica)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    out = out_dir / "fig03_cpu_util_timeline"
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
    keep_metrics = [
        "overall_avg_cpu_util",
        "overall_max_cpu_util",
        "overall_avg_mem_util",
        "overall_max_mem_util",
        "join_coverage",
        "join_sample_coverage",
        "join_avg_cpu_util",
        "join_max_cpu_util",
        "invoke_probe_join_match_ratio",
    ]
    df = df[df["metric"].isin(keep_metrics)].copy()
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value_num"])
    if df.empty:
        logger.warning("no numeric metrics in paper highlight; skip fig04")
        return None

    df = df.sort_values("value_num", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh(df["metric"], df["value_num"], color="#9467bd")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if isinstance(v, float) and v != int(v) else f"{int(v)}",
                ha="left", va="center", fontsize=9)
    ax.set_title("Resource Monitor Paper Highlight Metrics")
    ax.set_xlabel("Value")
    ax.grid(True, axis="x", alpha=0.3)

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
    input_dir, output_dir = resolve_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("input=%s output=%s", input_dir, output_dir)

    join_df = pd.read_csv(input_dir / "invocation_resource_join.csv", encoding="utf-8-sig")
    per_replica_df = pd.read_csv(input_dir / "resource_utilization_per_replica.csv", encoding="utf-8-sig")
    sample_probe_path = input_dir / "resource_monitor_sample_probe.csv"
    if sample_probe_path.exists():
        util_df = pd.read_csv(sample_probe_path, encoding="utf-8-sig")
    else:
        util_df = pd.read_csv(input_dir / "function_utilization.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "resource_monitor_paper_highlight.csv", encoding="utf-8-sig")

    fig01_per_invocation_cpu_util(join_df, output_dir)
    fig02_per_replica_util(per_replica_df, output_dir)
    fig03_cpu_util_timeline(util_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
