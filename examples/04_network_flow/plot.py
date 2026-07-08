"""
文件作用：network_flow 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_throughput_per_flow.png/pdf：每个 flow 的吞吐量（条形图）
  论文 demo 关键图 —— 对比 single_flow vs concurrent_bottleneck
- fig02_duration_per_flow.png/pdf：每个 flow 的传输耗时（条形图）
  直观展示 scaling_factor 的来源
- fig03_scaling_factor.png/pdf：同大小流下并发相对单流的延迟放大倍数（柱状图）
  论文 demo 关键数字：3 个并发流共享 10Mbps bottleneck 时延迟放大约 3 倍
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：04_network_flow/outputs/ 目录下的 CSV
输出：04_network_flow/figures/ 目录下的 png + pdf

运行：
    python -u examples/04_network_flow/plot.py
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


SCENARIO_COLOR = {
    "single_flow": "#2ca02c",
    "concurrent_bottleneck": "#d62728",
}

SCENARIO_ORDER = {
    "single_flow": 0,
    "concurrent_bottleneck": 1,
}


def sort_by_scenario(df: pd.DataFrame) -> pd.DataFrame:
    """
    按论文图叙事顺序排序：先 single baseline，再 concurrent bottleneck。
    """
    out = df.copy()
    out["_scenario_order"] = out["scenario"].map(SCENARIO_ORDER).fillna(99)
    return (
        out
        .sort_values(["_scenario_order", "flow_id"], ascending=[True, True])
        .drop(columns=["_scenario_order"])
        .reset_index(drop=True)
    )


def fig01_throughput_per_flow(perf_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    条形图：每个 flow 的吞吐量（Mbps）。

    论文 demo 关键图 —— single_flow 接近瓶颈带宽，concurrent 接近 1/3 公平份额。
    """
    if perf_df.empty or "throughput_mbps" not in perf_df.columns:
        logger.warning("perf df is empty; skip fig01")
        return None

    df = sort_by_scenario(perf_df)
    colors = df["scenario"].map(SCENARIO_COLOR).fillna("#7f7f7f")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(df["flow_id"], df["throughput_mbps"], color=colors)
    for bar, v in zip(bars, df["throughput_mbps"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.2f}",
                ha="center", va="bottom", fontsize=9)

    # 画一条 bottleneck 标称带宽参考线
    if "bottleneck_bandwidth_mbps" in df.columns:
        bw = df["bottleneck_bandwidth_mbps"].max()
        ax.axhline(y=bw, color="gray", linestyle="--", linewidth=1.0, alpha=0.7,
                   label=f"bottleneck = {bw} Mbps")
        concurrent_count = max(
            int((df["scenario"] == "concurrent_bottleneck").sum()),
            1,
        )
        ax.axhline(y=bw / concurrent_count, color="orange", linestyle=":", linewidth=1.0, alpha=0.7,
                   label=f"fair share = {bw/concurrent_count:.2f} Mbps")

    ax.set_title("Per-Flow Throughput: single vs concurrent bottleneck")
    ax.set_xlabel("Flow ID")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_ylim(0, max(12, df["throughput_mbps"].max() * 1.2))
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")

    # 颜色图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=SCENARIO_COLOR["single_flow"], label="single_flow"),
        Patch(facecolor=SCENARIO_COLOR["concurrent_bottleneck"], label="concurrent_bottleneck"),
    ]
    ax.legend(
        handles=ax.get_legend().legend_handles + legend_elements,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.28),
        ncol=2,
    )

    out = out_dir / "fig01_throughput_per_flow"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_duration_per_flow(perf_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    条形图：每个 flow 的传输耗时（秒）。
    """
    if perf_df.empty or "duration" not in perf_df.columns:
        logger.warning("perf df is empty; skip fig02")
        return None

    df = sort_by_scenario(perf_df)
    colors = df["scenario"].map(SCENARIO_COLOR).fillna("#7f7f7f")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(df["flow_id"], df["duration"], color=colors)
    for bar, v in zip(bars, df["duration"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.2f}s",
                ha="center", va="bottom", fontsize=9)

    ax.set_title("Per-Flow Duration: single vs concurrent bottleneck")
    ax.set_xlabel("Flow ID")
    ax.set_ylabel("Duration (s)")
    ax.grid(True, axis="y", alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=SCENARIO_COLOR["single_flow"], label="single_flow"),
        Patch(facecolor=SCENARIO_COLOR["concurrent_bottleneck"], label="concurrent_bottleneck"),
    ]
    ax.legend(handles=legend_elements, loc="upper left")

    out = out_dir / "fig02_duration_per_flow"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_scaling_factor(summary_df: pd.DataFrame, paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：scaling_factor（并发相对单流的延迟放大倍数）。

    论文 demo 关键数字：3 条同大小 flow 共享瓶颈时 scaling_factor 接近 3。
    """
    scaling = 0.0
    if not paper_df.empty and "scaling_factor" in paper_df["metric"].values:
        scaling = float(paper_df.loc[paper_df["metric"] == "scaling_factor", "value"].iloc[0])

    if not summary_df.empty and "scaling_factor" in summary_df.columns:
        concurrent_row = summary_df[summary_df["scenario"] == "concurrent_bottleneck"]
        if not concurrent_row.empty:
            scaling = float(concurrent_row["scaling_factor"].iloc[0])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    scenarios = ["single_flow", "concurrent_bottleneck"]
    factors = [1.0, scaling]
    colors = [SCENARIO_COLOR[s] for s in scenarios]
    bars = ax.bar(scenarios, factors, color=colors)
    for bar, v in zip(bars, factors):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}x", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_title("Scaling Factor for Equal-Size Flows")
    ax.set_ylabel("Scaling Factor (×)")
    ax.set_ylim(0, max(6.0, scaling * 1.3))
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig03_scaling_factor"
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
    if "metric" in df.columns:
        df = df[~df["metric"].isin(["all_flows_share_bottleneck"])].copy()
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value_num"])
    if df.empty:
        logger.warning("no numeric metrics in paper highlight; skip fig04")
        return None

    df = df.sort_values("value_num", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(df["metric"], df["value_num"], color="#9467bd")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if isinstance(v, float) and v != int(v) else f"{int(v)}",
                ha="left", va="center", fontsize=9)
    ax.set_title("Network Flow Paper Highlight Metrics")
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

    perf_df = pd.read_csv(input_dir / "network_flow_performance.csv", encoding="utf-8-sig")
    summary_df = pd.read_csv(input_dir / "network_flow_summary.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "network_flow_paper_highlight.csv", encoding="utf-8-sig")

    fig01_throughput_per_flow(perf_df, output_dir)
    fig02_duration_per_flow(perf_df, output_dir)
    fig03_scaling_factor(summary_df, paper_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
