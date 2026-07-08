"""
文件作用：Skippy 调度样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_pods_per_node.png/pdf：每个 node 上调度到的 pod 数（条形图）
  论文 demo 关键图 —— 直观看出 Skippy 默认调度器的节点分布倾向
- fig02_feasible_nodes_per_pod.png/pdf：每个 pod 的可行/过滤节点数（堆叠条形图）
  观察资源谓词过滤效果
- fig03_schedule_timeline.png/pdf：调度顺序与选中节点图
  显示每个 pod 的调度顺序、目标节点和是否需要拉镜像
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图
  包含 total_pods_scheduled / selected_node_count / entropy 等

输入：03_skippy_scheduler/outputs/ 目录下的 CSV
输出：03_skippy_scheduler/figures/ 目录下的 png + pdf

运行：
    python -u examples/03_skippy_scheduler/plot.py
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


def fig01_pods_per_node(node_stats_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    条形图：每个 node 调度到的 pod 数。
    """
    if node_stats_df.empty or "scheduled_pod_count" not in node_stats_df.columns:
        logger.warning("node stats is empty; skip fig01")
        return None

    df = node_stats_df.sort_values("scheduled_pod_count", ascending=False).copy()
    labels = df["node_name"].astype(str).tolist()
    counts = df["scheduled_pod_count"].astype(int).tolist()

    # 颜色梯度：scheduled_pod_count 越大颜色越深
    max_c = max(counts) if counts else 1
    colors = plt.cm.viridis(np.array(counts) / max(max_c, 1))

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, counts, color=colors)
    for bar, v in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(v)}",
                ha="center", va="bottom", fontsize=10)
    ax.set_title("Pods Scheduled per Node (Skippy Default Scheduler)")
    ax.set_xlabel("Selected Node")
    ax.set_ylabel("Scheduled Pod Count")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_pods_per_node"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_feasible_nodes_per_pod(feasible_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    堆叠条形图：每个 pod 的可行节点数 vs 被过滤节点数。

    论文 demo 关键图 —— 直观看出 Skippy 资源过滤对每个 pod 的影响。
    """
    if feasible_df.empty or "feasible_nodes_full" not in feasible_df.columns:
        logger.warning("feasible nodes per pod is empty; skip fig02")
        return None

    df = feasible_df.sort_values("pod_name").copy()
    if "all_nodes" in df.columns:
        df["filtered_nodes"] = df["all_nodes"].astype(int) - df["feasible_nodes_full"].astype(int)
    else:
        df["filtered_nodes"] = 0

    x = np.arange(len(df))

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    if "all_nodes" in df.columns:
        bars_feasible = ax.bar(
            x,
            df["feasible_nodes_full"],
            color="steelblue",
            label="feasible",
        )
        bars_filtered = ax.bar(
            x,
            df["filtered_nodes"],
            bottom=df["feasible_nodes_full"],
            color="#d95f02",
            alpha=0.75,
            label="filtered",
        )
    else:
        bars_feasible = ax.bar(x, df["feasible_nodes_full"], color="steelblue", label="feasible")
        bars_filtered = []

    for bar, v in zip(bars_feasible, df["feasible_nodes_full"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            max(bar.get_height() / 2, 0.15),
            f"{int(v)}",
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            fontweight="bold",
        )
    for bar, feasible, filtered in zip(bars_filtered, df["feasible_nodes_full"], df["filtered_nodes"]):
        if int(filtered) <= 0:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            feasible + filtered / 2,
            f"-{int(filtered)}",
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            fontweight="bold",
        )

    # 标注每个 pod 的 selected_node
    if "selected_node" in df.columns:
        for i, sn in enumerate(df["selected_node"]):
            ax.text(i, -0.35, f"-> {sn}", ha="center", va="top",
                    fontsize=8, color="#d62728", rotation=15)

    ax.set_xticks(x)
    ax.set_xticklabels(df["pod_name"], rotation=20, ha="right")
    ax.set_ylabel("Node count")
    ax.set_title("Skippy Resource Filtering per Pod")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(-0.8, max(df.get("all_nodes", df["feasible_nodes_full"]).max() + 0.5, 1))

    out = out_dir / "fig02_feasible_nodes_per_pod"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_schedule_timeline(result_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    调度顺序图：x=pod 序号，y=selected_node。

    Skippy 调度动作在仿真时间上几乎瞬时完成，直接画 simtime 轴可读性差。
    这里保留调度顺序，并把目标节点作为 y 轴，更适合展示调度选择结果。
    """
    if result_df.empty or "pod_name" not in result_df.columns or "selected_node" not in result_df.columns:
        logger.warning("result df has no pod_name/selected_node; skip fig03")
        return None

    df = result_df.sort_values("simtime").reset_index(drop=True).copy()
    x = np.arange(len(df))
    node_order = sorted(df["selected_node"].astype(str).unique().tolist())
    node_to_y = {node: i for i, node in enumerate(node_order)}
    y = df["selected_node"].astype(str).map(node_to_y)
    colors = ["#d62728" if c > 0 else "#2ca02c"
              for c in df.get("needed_images_count", [0] * len(df))]

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.scatter(x, y, s=150, c=colors, zorder=5, edgecolors="black", linewidths=1.0)
    ax.plot(x, y, color="#1f77b4", alpha=0.35, linewidth=1.2, zorder=1)

    for i, row in df.iterrows():
        simtime = row.get("simtime", None)
        suffix = f"\nt={float(simtime):.4f}s" if simtime is not None else ""
        ax.annotate(
            f"{row['pod_name']}{suffix}",
            xy=(i, y.iloc[i]),
            xytext=(8, 8 if i % 2 == 0 else -18),
            textcoords="offset points",
            fontsize=8,
            color="black",
        )

    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i+1}" for i in x])
    ax.set_yticks(range(len(node_order)))
    ax.set_yticklabels(node_order)
    ax.set_xlabel("Pod scheduling order")
    ax.set_ylabel("Selected node")
    ax.set_title("Skippy Scheduling Order and Selected Node")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-0.6, len(node_order) - 0.4)

    # 图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d62728",
               markersize=10, label="needs image pull"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ca02c",
               markersize=10, label="image cached"),
    ]
    ax.legend(handles=legend_elements, loc="upper left")

    out = out_dir / "fig03_schedule_timeline"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画数值型 metric（跳过 bool 型 probe_invocation_consistent），
    便于一眼看出 Skippy 默认调度的关键数字。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    df = paper_df.copy()
    if "metric" in df.columns:
        df = df[~df["metric"].isin(["probe_invocation_consistent"])].copy()
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value_num"])
    if df.empty:
        logger.warning("no numeric metrics in paper highlight; skip fig04")
        return None

    df = df.sort_values("value_num", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(df["metric"], df["value_num"], color="#9467bd")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if isinstance(v, float) and v != int(v) else f"{int(v)}",
                ha="left", va="center", fontsize=9)
    ax.set_title("Skippy Scheduler Paper Highlight Metrics")
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

    node_stats_df = pd.read_csv(input_dir / "skippy_node_scheduling_stats.csv", encoding="utf-8-sig")
    feasible_df = pd.read_csv(input_dir / "skippy_feasible_nodes_per_pod.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "skippy_paper_highlight.csv", encoding="utf-8-sig")
    result_df = pd.read_csv(input_dir / "skippy_scheduler_result.csv", encoding="utf-8-sig")

    fig01_pods_per_node(node_stats_df, output_dir)
    fig02_feasible_nodes_per_pod(feasible_df, output_dir)
    fig03_schedule_timeline(result_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
