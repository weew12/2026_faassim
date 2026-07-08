"""
文件作用：topologies 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_topology_size_comparison.png/pdf：4 个拓扑的节点数 / 边数 / 路由数对比柱状图
  论文 demo 关键图 —— 直观对比 minimal/edge_cloud_star/bottleneck/urban_sensing 的规模差异
- fig02_per_topology_node_distribution.png/pdf：每个拓扑的节点类型分布
  （Node / Link / Switch 堆叠柱状图）
- fig03_route_overview.png/pdf：每个拓扑的 route rtt_ms / hop_count / bottleneck_bandwidth 对比
  直观看出不同拓扑的路由特征
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：09_topologies/outputs/ 目录下的 CSV
输出：09_topologies/figures/ 目录下的 png + pdf

运行：
    python -u examples/09_topologies/plot.py
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


def save_figure(fig, out: Path) -> None:
    """
    同时保存 png/pdf，避免每张图重复写保存循环。
    """
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    logger.info("saved %s (.png/.pdf)", out)


def resolve_dirs() -> tuple[Path, Path]:
    """
    解析输入 / 输出目录。
    """
    here = Path(__file__).resolve().parent
    return here / "outputs", here / "figures"


TOPOLOGY_COLOR = {
    "minimal": "#2ca02c",
    "edge_cloud_star": "#1f77b4",
    "bottleneck": "#ff7f0e",
    "urban_sensing": "#d62728",
}
TOPOLOGY_ORDER = ["minimal", "edge_cloud_star", "bottleneck", "urban_sensing"]


def fig01_topology_size_comparison(summary_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    4 个拓扑的节点数 / 边数 / 路由数对比柱状图（论文 demo 关键图）。
    """
    if summary_df.empty:
        logger.warning("summary_df is empty; skip fig01")
        return None

    df = summary_df.copy()
    df["topology"] = pd.Categorical(df["topology"], categories=TOPOLOGY_ORDER, ordered=True)
    df = df.sort_values("topology")

    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(df))
    width = 0.27

    bars1 = ax.bar(x - width, df["graph_node_count"], width,
                   label="graph_node_count", color="#1f77b4")
    bars2 = ax.bar(x, df["graph_edge_count"], width,
                   label="graph_edge_count", color="#ff7f0e")
    bars3 = ax.bar(x + width, df["route_records"], width,
                   label="route_records", color="#2ca02c")

    for bar, v in zip(bars1, df["graph_node_count"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{int(v)}", ha="center", va="bottom", fontsize=8)
    for bar, v in zip(bars2, df["graph_edge_count"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{int(v)}", ha="center", va="bottom", fontsize=8)
    for bar, v in zip(bars3, df["route_records"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{int(v)}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(df["topology"], rotation=15, ha="right")
    ax.set_ylabel("count")
    ax.set_title("Topology size: graph nodes vs edges vs routes (4 topologies)")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig01_topology_size_comparison"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig02_per_topology_node_distribution(nodes_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每个拓扑的节点类型分布（Node / Link / Switch 堆叠柱状图）。
    """
    if nodes_df.empty or "object_type" not in nodes_df.columns:
        logger.warning("nodes_df is empty; skip fig02")
        return None

    df = nodes_df.copy()

    # 按 topology × object_type 聚合
    pivot = (
        df.groupby(["topology", "object_type"]).size().reset_index(name="count")
        .pivot(index="topology", columns="object_type", values="count")
        .fillna(0)
    )
    pivot = pivot.reindex([name for name in TOPOLOGY_ORDER if name in pivot.index])

    # 固定列顺序
    preferred = ["node", "link", "switch"]
    for col in preferred:
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot[preferred]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    pivot.plot(
        kind="bar",
        stacked=True,
        ax=ax,
        color=["#2ca02c", "#ff7f0e", "#9467bd"],
        edgecolor="black",
        linewidth=0.5,
    )

    ax.set_xlabel("Topology")
    ax.set_ylabel("Object count (stacked)")
    ax.set_title("Per-Topology Node Type Distribution (Node / Link / Switch)")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=15, ha="right")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_per_topology_node_distribution"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig03_route_overview(routes_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每个拓扑的 route 概览：rtt_ms / hop_count / bottleneck_bandwidth 对比。
    """
    if routes_df.empty:
        logger.warning("routes_df is empty; skip fig03")
        return None

    df = routes_df.copy()
    # 只看 route_available=True 的记录
    if "route_available" in df.columns:
        df = df[df["route_available"] == True].copy()

    if df.empty:
        logger.warning("no available routes; skip fig03")
        return None

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    topology_order = [name for name in TOPOLOGY_ORDER if name in set(df["topology"])]
    x_positions = {name: index for index, name in enumerate(topology_order)}

    def scatter_metric(ax, metric: str) -> None:
        for fn in topology_order:
            sub = df[df["topology"] == fn].reset_index(drop=True)
            color = TOPOLOGY_COLOR.get(fn, "#7f7f7f")
            offsets = np.linspace(-0.08, 0.08, len(sub)) if len(sub) > 1 else np.array([0.0])
            ax.scatter(
                x_positions[fn] + offsets,
                sub[metric],
                s=70,
                color=color,
                alpha=0.75,
                edgecolors="black",
                linewidths=0.5,
                label=fn,
            )
        ax.set_xticks(list(x_positions.values()))
        ax.set_xticklabels(list(x_positions.keys()), rotation=15, ha="right")

    # 左图：rtt_ms by topology
    ax = axes[0]
    if "rtt_ms" in df.columns:
        scatter_metric(ax, "rtt_ms")
        ax.set_ylabel("rtt (ms)")
        ax.set_title("Per-Topology Route RTT")
        ax.grid(True, axis="y", alpha=0.3)

    # 右图：hop_count by topology
    ax = axes[1]
    if "hop_count" in df.columns:
        scatter_metric(ax, "hop_count")
        ax.set_ylabel("hop count")
        ax.set_title("Per-Topology Route Hop Count")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)

    # 右图：bottleneck bandwidth by topology
    ax = axes[2]
    if "bottleneck_bandwidth_mbps" in df.columns:
        scatter_metric(ax, "bottleneck_bandwidth_mbps")
        ax.set_ylabel("bottleneck bandwidth (Mbps)")
        ax.set_title("Route Bottleneck Bandwidth")
        ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()

    out = out_dir / "fig03_route_overview"
    save_figure(fig, out)
    plt.close(fig)
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
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh(df["metric"], df["value_num"], color="#9467bd")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if isinstance(v, float) and v != int(v) else f"{int(v)}",
                ha="left", va="center", fontsize=9)
    ax.set_title("Topology Paper Highlight Metrics")
    ax.set_xlabel("Value")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig04_paper_highlight_metrics"
    save_figure(fig, out)
    plt.close(fig)
    return out


def main() -> None:
    """
    入口：读取 outputs/ 下的 CSV，输出 figures/ 下的 png+pdf。
    """
    configure_logging()
    input_dir, output_dir = resolve_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("input=%s output=%s", input_dir, output_dir)

    summary_df = pd.read_csv(input_dir / "topology_summary.csv", encoding="utf-8-sig")
    nodes_df = pd.read_csv(input_dir / "topology_nodes.csv", encoding="utf-8-sig")
    routes_df = pd.read_csv(input_dir / "topology_routes.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "topology_paper_highlight.csv", encoding="utf-8-sig")

    fig01_topology_size_comparison(summary_df, output_dir)
    fig02_per_topology_node_distribution(nodes_df, output_dir)
    fig03_route_overview(routes_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
