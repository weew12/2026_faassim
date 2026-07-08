"""
文件作用：fault_model 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_request_timeline_with_fault_windows.png/pdf：
  每次请求按 simtime 散点，叠加故障窗口阴影
  （红色 = node_outage [1.0, 1.8]、橙色 = network_degradation [2.2, 3.6]）。
  论文 demo 关键图 —— 视觉证明 node_outage / network_degradation 请求
  严格落在故障窗口内。
- fig02_fault_reason_distribution.png/pdf：按 reason 的请求数柱状图
  （normal / replica_error / node_outage / network_degradation）。
- fig03_per_request_final_duration.png/pdf：每次请求的 final_duration
  散点（按 simtime 排序），颜色按 reason；可直观看到网络退化把
  base_duration 0.25s 放大到 0.70s，失败请求被压到 0.03s。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图。

输入：11_fault_model/outputs/ 目录下的 CSV
输出：11_fault_model/figures/ 目录下的 png + pdf

运行：
    python -u examples/11_fault_model/plot.py
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


REASON_COLORS = {
    "normal": "#2ca02c",
    "replica_error": "#9467bd",
    "node_outage": "#d62728",
    "network_degradation": "#ff7f0e",
}
REASON_ORDER = ["normal", "replica_error", "node_outage", "network_degradation"]


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
        description="Generate paper-demo figures for 11_fault_model.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/11_fault_model/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/11_fault_model/figures.",
    )
    return parser.parse_args()


def save_figure(fig, out: Path) -> None:
    """
    同时保存 png/pdf。
    """
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    logger.info("saved %s (.png/.pdf)", out)


def fig01_request_timeline_with_fault_windows(
    probe_with_sim_df: pd.DataFrame,
    fault_events_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    请求时间线 + 故障窗口阴影。

    - x 轴：probe 重建 simtime
    - y 轴：probe 序号（按 simtime 升序）
    - 颜色：reason
    - 红色阴影 = node_outage 窗口
    - 橙色阴影 = network_degradation 窗口
    """
    if probe_with_sim_df.empty or "simtime" not in probe_with_sim_df.columns:
        logger.warning("probe_with_simtime is empty; skip fig01")
        return None

    df = probe_with_sim_df.copy()
    df["simtime"] = pd.to_numeric(df["simtime"], errors="coerce")
    df = df.dropna(subset=["simtime"]).sort_values("simtime").reset_index(drop=True)
    if df.empty:
        logger.warning("probe_with_simtime has no valid simtime; skip fig01")
        return None

    df["seq"] = np.arange(1, len(df) + 1)
    if "reason" not in df.columns:
        df["reason"] = "normal"

    fig, ax = plt.subplots(figsize=(9, 4.5))

    # 画故障窗口阴影
    fault_band_specs = [
        ("node_outage", "#d62728", "node_outage window"),
        ("network_degradation", "#ff7f0e", "network_degradation window"),
    ]
    if not fault_events_df.empty and "fault_type" in fault_events_df.columns:
        for ftype, color, label in fault_band_specs:
            sub = fault_events_df[fault_events_df["fault_type"] == ftype]
            for _, ev in sub.iterrows():
                ax.axvspan(
                    float(ev["start_time"]),
                    float(ev["end_time"]),
                    color=color,
                    alpha=0.12,
                    label=label,
                )

    # 散点按 reason
    for reason in REASON_ORDER:
        sub = df[df["reason"] == reason]
        if sub.empty:
            continue
        ax.scatter(
            sub["simtime"],
            sub["seq"],
            s=42,
            color=REASON_COLORS[reason],
            edgecolors="black",
            linewidths=0.4,
            label=f"{reason} (n={len(sub)})",
            zorder=3,
        )

    ax.set_title("Request Timeline vs Fault Windows (server_0)")
    ax.set_xlabel("Simtime (s)")
    ax.set_ylabel("Request sequence (by simtime)")
    ax.grid(True, alpha=0.3)
    # 去重 legend（axvspan 每个窗口都打 label，dedup）
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    deduped = []
    deduped_labels = []
    for h, l in zip(handles, labels):
        if l not in seen:
            deduped.append(h)
            deduped_labels.append(l)
            seen.add(l)
    ax.legend(deduped, deduped_labels, loc="upper left", fontsize=8, ncol=2)

    out = out_dir / "fig01_request_timeline_with_fault_windows"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig02_fault_reason_distribution(reason_dist_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    故障原因分布柱状图。
    """
    if reason_dist_df.empty or "reason" not in reason_dist_df.columns:
        logger.warning("fault reason distribution is empty; skip fig02")
        return None

    df = reason_dist_df.copy()
    grp = df.groupby("reason").agg(request_count=("request_count", "sum")).reset_index()
    grp["reason"] = grp["reason"].astype(str)
    grp["__order__"] = grp["reason"].apply(
        lambda r: REASON_ORDER.index(r) if r in REASON_ORDER else len(REASON_ORDER)
    )
    grp = grp.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(
        grp["reason"],
        grp["request_count"],
        color=[REASON_COLORS.get(r, "#7f7f7f") for r in grp["reason"]],
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, grp["request_count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{int(v)}",
            ha="center",
            va="bottom",
        )
    ax.set_title("Fault Reason Distribution (per-request count)")
    ax.set_xlabel("Reason")
    ax.set_ylabel("Request count")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_fault_reason_distribution"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig03_per_request_final_duration(probe_with_sim_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每次请求的 final_duration 散点（按 simtime 排序），颜色按 reason。
    """
    if probe_with_sim_df.empty or "simtime" not in probe_with_sim_df.columns:
        logger.warning("probe_with_simtime is empty; skip fig03")
        return None

    df = probe_with_sim_df.copy()
    df["simtime"] = pd.to_numeric(df["simtime"], errors="coerce")
    if "final_duration" in df.columns:
        df["final_duration"] = pd.to_numeric(df["final_duration"], errors="coerce")
    df = df.dropna(subset=["simtime", "final_duration"]).sort_values("simtime").reset_index(drop=True)
    if df.empty:
        logger.warning("no valid (simtime, final_duration); skip fig03")
        return None
    if "reason" not in df.columns:
        df["reason"] = "normal"

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for reason in REASON_ORDER:
        sub = df[df["reason"] == reason]
        if sub.empty:
            continue
        ax.scatter(
            sub["simtime"],
            sub["final_duration"],
            s=46,
            color=REASON_COLORS[reason],
            edgecolors="black",
            linewidths=0.4,
            label=f"{reason} (n={len(sub)})",
            zorder=3,
        )

    # 画基线：base_duration = 0.25
    ax.axhline(0.25, color="#2ca02c", linestyle="--", linewidth=1.0, alpha=0.6,
               label="base_duration = 0.25s")
    # 画 network_degradation 加成后的水平：0.25 + 0.45 = 0.70
    ax.axhline(0.70, color="#ff7f0e", linestyle="--", linewidth=1.0, alpha=0.6,
               label="base + extra_delay = 0.70s")
    # 画 failure_latency = 0.03
    ax.axhline(0.03, color="#d62728", linestyle="--", linewidth=1.0, alpha=0.6,
               label="failure_latency = 0.03s")

    ax.set_title("Per-Request final_duration vs Simtime")
    ax.set_xlabel("Simtime (s)")
    ax.set_ylabel("final_duration (s)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=8, ncol=3)

    out = out_dir / "fig03_per_request_final_duration"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画数值型 metric（跳过 bool 型），便于一眼看出故障模型的关键数字。
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

    # 按 value 排序，从小到大
    df = df.sort_values("value_num", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.barh(df["metric"], df["value_num"], color="#4c78a8")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}",
            ha="left",
            va="center",
        )
    ax.set_title("Fault Model Paper Highlight Metrics")
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
    args = parse_args()
    input_dir, output_dir = args.input_dir, args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("input=%s output=%s", input_dir, output_dir)

    probe_with_sim_df = pd.read_csv(input_dir / "probe_with_simtime.csv", encoding="utf-8-sig")
    reason_dist_df = pd.read_csv(input_dir / "fault_reason_distribution.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "fault_model_paper_highlight.csv", encoding="utf-8-sig")
    fault_events_df = pd.read_csv(input_dir / "fault_events.csv", encoding="utf-8-sig")

    fig01_request_timeline_with_fault_windows(probe_with_sim_df, fault_events_df, output_dir)
    fig02_fault_reason_distribution(reason_dist_df, output_dir)
    fig03_per_request_final_duration(probe_with_sim_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
