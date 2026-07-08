"""
文件作用：data_locality 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_aware_vs_forced_comparison.png/pdf：两个场景的 total_download_duration 柱状图
  论文 demo 关键图 —— 直观看 speedup_ratio_forced_over_aware ≈ 20×
- fig02_candidate_estimates.png/pdf：edge_near / edge_mid / edge_far 估算下载时间柱状图
  直观看出 Skippy DataLocalityPriority 对不同候选节点的预估
- fig03_download_timeline.png/pdf：simtime vs download_duration（两个场景叠加）
  论文 demo 关键图 —— aware 早完成 / forced 晚完成
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：10_data_locality/outputs/ 目录下的 CSV
输出：10_data_locality/figures/ 目录下的 png + pdf

运行：
    python -u examples/10_data_locality/plot.py
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


def save_figure(fig, out: Path) -> None:
    """
    同时保存 png/pdf。
    """
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    logger.info("saved %s (.png/.pdf)", out)


SCENARIO_COLOR = {
    "data_locality_aware": "#2ca02c",
    "forced_remote": "#d62728",
}


def fig01_aware_vs_forced_comparison(comparison_df: pd.DataFrame, paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：两个场景的 total_download_duration 对比（论文 demo 关键图）。
    """
    if comparison_df.empty:
        logger.warning("comparison_df is empty; skip fig01")
        return None

    df = comparison_df.copy()

    speedup = 0.0
    if not paper_df.empty and "speedup_ratio_forced_over_aware" in paper_df["metric"].values:
        speedup = float(paper_df.loc[paper_df["metric"] == "speedup_ratio_forced_over_aware", "value"].iloc[0])

    fig, ax = plt.subplots(figsize=(8, 5))
    scenarios = df["scenario"].tolist()
    durations = df["total_download_duration"].astype(float).tolist()
    colors = [SCENARIO_COLOR.get(s, "#7f7f7f") for s in scenarios]

    bars = ax.bar(scenarios, durations, color=colors)
    for bar, v in zip(bars, durations):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.2f}s", ha="center", va="bottom", fontsize=11)

    ax.set_xlabel("Scenario")
    ax.set_ylabel("total_download_duration (simtime seconds)")
    ax.set_title(f"Data Locality Awareness: forced_remote is {speedup:.1f}x slower")
    ax.grid(True, axis="y", alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=SCENARIO_COLOR["data_locality_aware"], label="data_locality_aware (Skippy DataLocality)"),
        Patch(facecolor=SCENARIO_COLOR["forced_remote"], label="forced_remote (ForcedNodeScheduler)"),
    ]
    ax.legend(handles=legend_elements, loc="upper left")

    out = out_dir / "fig01_aware_vs_forced_comparison"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig02_candidate_estimates(join_aware_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：edge_near / edge_mid / edge_far 的估算下载时间 + 实际下载时间（仅 aware 场景）。
    """
    if join_aware_df.empty or "estimated_download_time" not in join_aware_df.columns:
        logger.warning("join_aware_df is empty; skip fig02")
        return None

    df = join_aware_df.copy()

    fig, ax = plt.subplots(figsize=(9, 4.8))
    df["estimated_download_time"] = pd.to_numeric(df["estimated_download_time"], errors="coerce")
    if "actual_download_duration" in df.columns:
        df["actual_download_duration"] = pd.to_numeric(df["actual_download_duration"], errors="coerce")

    x = np.arange(len(df))
    width = 0.36

    # Skippy 估算
    bars_est = ax.bar(
        x - width / 2,
        df["estimated_download_time"],
        width=width,
        color="#9467bd",
        alpha=0.85,
        label="estimated (Skippy DataLocalityPriority)",
    )
    for bar, v in zip(bars_est, df["estimated_download_time"]):
        if pd.notna(v):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v:.2f}s", ha="center", va="bottom", fontsize=9)

    # 实际下载（如果有 actual_download_duration 列）
    if "actual_download_duration" in df.columns:
        actual_subset = df[df["actual_download_duration"].notna()].copy()
        if not actual_subset.empty:
            actual_x = [df.index.get_loc(idx) + width / 2 for idx in actual_subset.index]
            bars_act = ax.bar(
                actual_x,
                actual_subset["actual_download_duration"],
                width=width,
                color="#1f77b4",
                alpha=0.75,
                label="actual selected node (simulate_data_download)",
            )
            for bar, v in zip(bars_act, actual_subset["actual_download_duration"]):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{v:.2f}s", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(df["candidate_node"])
    ax.set_xlabel("Candidate Node")
    ax.set_ylabel("download time (simtime seconds)")
    ax.set_title("DataLocalityPriority estimates per candidate node (data_locality_aware scenario)")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_candidate_estimates"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig03_download_timeline(out_dir: Path) -> Path:
    """
    时序图：simtime vs download_duration（两个场景叠加）。
    """
    fig, ax = plt.subplots(figsize=(9, 4.5))

    has_data = False
    max_t_end = 0.0
    for scenario_name, color in SCENARIO_COLOR.items():
        download_path = Path(__file__).resolve().parent / "outputs" / scenario_name / "data_locality_download.csv"
        if not download_path.exists():
            continue
        df = pd.read_csv(download_path, encoding="utf-8-sig")
        if df.empty or "t_start" not in df.columns or "download_duration" not in df.columns:
            continue
        df["t_start"] = pd.to_numeric(df["t_start"], errors="coerce")
        df["download_duration"] = pd.to_numeric(df["download_duration"], errors="coerce")
        df = df.dropna(subset=["t_start", "download_duration"])
        if df.empty:
            continue

        # 阶梯图：t_start → t_start + download_duration
        for _, row in df.iterrows():
            t_start = float(row["t_start"])
            duration = float(row["download_duration"])
            t_end = t_start + duration
            max_t_end = max(max_t_end, t_end)
            ax.plot([t_start, t_end], [duration, duration],
                    color=color, linewidth=4.0, alpha=0.85,
                    label=scenario_name if _ == 0 else None)
            ax.scatter([t_start, t_end], [duration, duration],
                       color=color, s=60, zorder=5, edgecolors="black", linewidths=0.5)
            ax.annotate(
                f"{row['node_name']}",
                xy=((t_start + t_end) / 2, duration),
                xytext=(-6, 6),
                textcoords="offset points",
                va="bottom",
                ha="center",
                fontsize=8,
                color=color,
            )
        has_data = True

    if not has_data:
        logger.warning("no download timeline data; skip fig03")
        plt.close(fig)
        return None

    ax.set_xlabel("simtime (s)")
    ax.set_ylabel("download_duration (simtime seconds)")
    ax.set_title("Data Download Timeline: aware (early) vs forced (late)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0, right=max_t_end * 1.08 if max_t_end > 0 else None)

    out = out_dir / "fig03_download_timeline"
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
    ax.set_title("Data Locality Paper Highlight Metrics")
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

    comparison_df = pd.read_csv(input_dir / "data_locality_comparison.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "data_locality_paper_highlight.csv", encoding="utf-8-sig")

    # aware 场景的 candidate_vs_actual_join
    join_aware_path = input_dir / "data_locality_aware" / "candidate_vs_actual_join.csv"
    if join_aware_path.exists():
        join_aware_df = pd.read_csv(join_aware_path, encoding="utf-8-sig")
    else:
        join_aware_df = pd.DataFrame()

    fig01_aware_vs_forced_comparison(comparison_df, paper_df, output_dir)
    fig02_candidate_estimates(join_aware_df, output_dir)
    fig03_download_timeline(output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
