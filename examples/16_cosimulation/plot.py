"""
文件作用：cosimulation 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_per_phase_impact.png/pdf：
  每个 phase 的 avg_final_duration + impact_relative_to_normal 倍数。
  论文 demo 关键图 —— 视觉证明外部控制器能在不同阶段放大/缩小 invoke 耗时。
- fig02_per_phase_invoke_events.png/pdf：
  每个 phase 的 probe 记录 invoke 次数柱状图。
- fig03_cosim_timeline.png/pdf：
  36 个 invoke 散点（simtime vs final_duration），颜色按 phase_name，
  叠加 trace 阶段阴影（绿色=normal / 红色=edge_pressure / 橙色=network_slowdown / 蓝色=cooldown）。
  论文 demo 关键图 —— 视觉展示 cosim 控制器影响与 trace 阶段对应，边界处允许少量 phase lag。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标分组条形图。

输入：16_cosimulation/outputs/ 目录下的 CSV
输出：16_cosimulation/figures/ 目录下的 png + pdf

运行：
    python -u examples/16_cosimulation/plot.py
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


PHASE_COLORS = {
    "normal": "#2ca02c",
    "edge_pressure": "#d62728",
    "network_slowdown": "#ff7f0e",
    "cooldown": "#1f77b4",
    "idle": "#7f7f7f",
}
PHASE_ORDER = ["normal", "edge_pressure", "network_slowdown", "cooldown"]


def short_metric_label(metric: str) -> str:
    """
    压缩 paper_highlight 的 metric 标签，避免图 04 轴标签过长。
    """
    replacements = {
        "impact_relative_to_normal": "impact",
        "avg_final_duration": "avg_duration",
        "invoke_events": "invokes",
        "exchange_events": "exchanges",
        "trace_runtime_factor": "trace_factor",
        "trace_network_delay": "trace_delay",
        "network_slowdown": "net_slow",
        "edge_pressure": "edge",
        "scale_attention": "scale",
        "network_attention": "network",
        "release_attention": "release",
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
        description="Generate paper-demo figures for 16_cosimulation.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/16_cosimulation/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/16_cosimulation/figures.",
    )
    return parser.parse_args()


def fig01_per_phase_impact(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每个 phase 的 avg_final_duration + impact_relative_to_normal 倍数。

    论文 demo 关键图。
    """
    if paper_df.empty or "metric" not in paper_df.columns or "value" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig01")
        return None

    df = paper_df[paper_df["metric"].str.startswith("avg_final_duration__")].copy()
    if df.empty:
        logger.warning("no avg_final_duration rows; skip fig01")
        return None

    df["phase_action"] = df["metric"].str.replace("avg_final_duration__", "", regex=False)
    # phase / action 拆分
    df["__phase__"] = df["phase_action"].apply(
        lambda s: s.split("__")[0] if "__" in s else s
    )
    df["__order__"] = df["__phase__"].apply(
        lambda p: PHASE_ORDER.index(p) if p in PHASE_ORDER else len(PHASE_ORDER)
    )
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)
    df["duration_num"] = pd.to_numeric(df["value"], errors="coerce")

    # impact_relative_to_normal
    impact_df = paper_df[paper_df["metric"].str.startswith("impact_relative_to_normal__")].copy()
    impact_map = {}
    if not impact_df.empty:
        for _, row in impact_df.iterrows():
            key = row["metric"].replace("impact_relative_to_normal__", "")
            try:
                impact_map[key] = float(row["value"])
            except Exception:
                pass

    # normal phase 也赋值 1.0（基线）
    for phase_action in df["phase_action"]:
        if phase_action not in impact_map:
            impact_map[phase_action] = 1.0

    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    colors = [PHASE_COLORS.get(p, "#7f7f7f") for p in df["__phase__"]]
    bars = ax.barh(
        df["phase_action"].map(short_metric_label),
        df["duration_num"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for i, (bar, v) in enumerate(zip(bars, df["duration_num"])):
        phase_action = df["phase_action"].iloc[i]
        impact = impact_map.get(phase_action, 1.0)
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{v:.3f}s ({impact:.2f}x)",
            ha="left",
            va="center",
        )
    ax.set_title("Per-phase avg_final_duration (impact vs normal)")
    ax.set_xlabel("avg_final_duration (s)")
    ax.grid(True, axis="x", alpha=0.3)

    out = out_dir / "fig01_per_phase_impact"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_phase_invoke_events(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    每个 phase 的 probe 记录 invoke 次数柱状图。
    """
    if paper_df.empty or "metric" not in paper_df.columns or "value" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig02")
        return None

    df = paper_df[paper_df["metric"].str.startswith("invoke_events__")].copy()
    if df.empty:
        logger.warning("no invoke_events rows; skip fig02")
        return None

    df["phase_action"] = df["metric"].str.replace("invoke_events__", "", regex=False)
    df["__phase__"] = df["phase_action"].apply(
        lambda s: s.split("__")[0] if "__" in s else s
    )
    df["__order__"] = df["__phase__"].apply(
        lambda p: PHASE_ORDER.index(p) if p in PHASE_ORDER else len(PHASE_ORDER)
    )
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)
    df["events_num"] = pd.to_numeric(df["value"], errors="coerce")

    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    colors = [PHASE_COLORS.get(p, "#7f7f7f") for p in df["__phase__"]]
    bars = ax.bar(
        df["phase_action"].map(short_metric_label),
        df["events_num"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, df["events_num"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{int(v)}",
            ha="center",
            va="bottom",
        )
    ax.set_title("Per-phase probe invoke_events")
    ax.set_xlabel("phase / action")
    ax.set_ylabel("invoke_events (probe count)")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_per_phase_invoke_events"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cosim_timeline(
    probe_df: pd.DataFrame,
    trace_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    cosim 时间线：36 个 invoke 散点（simtime vs final_duration），颜色按 phase_name。
    叠加 trace 阶段阴影。
    """
    if probe_df.empty or "simtime" not in probe_df.columns or "final_duration" not in probe_df.columns:
        logger.warning("probe df is empty or missing columns; skip fig03")
        return None

    df = probe_df.copy()
    df["simtime"] = pd.to_numeric(df["simtime"], errors="coerce")
    df["final_duration"] = pd.to_numeric(df["final_duration"], errors="coerce")
    df = df.dropna(subset=["simtime", "final_duration"])
    if df.empty:
        logger.warning("no valid (simtime, final_duration); skip fig03")
        return None
    if "phase_name" not in df.columns:
        df["phase_name"] = "normal"

    fig, ax = plt.subplots(figsize=(11, 4.8), constrained_layout=True)

    # 画 trace 阶段阴影
    if not trace_df.empty and "phase_name" in trace_df.columns:
        for _, trow in trace_df.iterrows():
            phase = str(trow["phase_name"])
            color = PHASE_COLORS.get(phase, "#7f7f7f")
            start = float(trow["start_time"])
            end = float(trow["start_time"]) + float(trow["duration"])
            ax.axvspan(
                start,
                end,
                color=color,
                alpha=0.08,
                label=f"trace {phase}",
            )

    # 按 phase 画散点
    for phase in PHASE_ORDER:
        sub = df[df["phase_name"] == phase]
        if sub.empty:
            continue
        ax.scatter(
            sub["simtime"],
            sub["final_duration"],
            s=80,
            color=PHASE_COLORS.get(phase, "#7f7f7f"),
            edgecolors="black",
            linewidths=0.5,
            label=f"{phase} (n={len(sub)})",
            zorder=3,
        )

    # 画 base_duration 参考线
    ax.axhline(0.18, color="#2ca02c", linestyle=":", linewidth=1.0, alpha=0.5,
               label="base_duration = 0.18s")
    # 画 network_slowdown 加成后 0.448s
    ax.axhline(0.448, color="#ff7f0e", linestyle=":", linewidth=1.0, alpha=0.5,
               label="network_slowdown level = 0.448s")
    # 画 edge_pressure 加成后 0.323s
    ax.axhline(0.323, color="#d62728", linestyle=":", linewidth=1.0, alpha=0.5,
               label="edge_pressure level = 0.323s")

    ax.set_title("Co-simulation timeline: invoke final_duration vs simtime (per phase)")
    ax.set_xlabel("Simtime (s)")
    ax.set_ylabel("final_duration (s)")
    ax.grid(True, alpha=0.3)
    # 去重 legend
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    deduped = []
    deduped_labels = []
    for h, l in zip(handles, labels):
        if l not in seen:
            deduped.append(h)
            deduped_labels.append(l)
            seen.add(l)
    ax.legend(
        deduped,
        deduped_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        fontsize=7,
        ncol=3,
        framealpha=0.9,
    )

    out = out_dir / "fig03_cosim_timeline"
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
        | df["metric"].isin(["phase_summary_count", "exchange_summary_count"])
        | df["metric"].str.startswith("invoke_events__")
        | df["metric"].str.startswith("exchange_events__")
        | df["metric"].str.startswith("trace_rps__")
    )
    count_df = df[count_mask].sort_values("value_num", ascending=True)
    effect_df = df[~count_mask].sort_values("value_num", ascending=True)

    fig, axes = plt.subplots(1, 2, figsize=(18, 9), constrained_layout=True)

    panels = [
        (axes[0], count_df, "Counts and trace RPS", "#4c78a8"),
        (axes[1], effect_df, "Duration, impact and trace factors", "#f58518"),
    ]
    for ax, panel_df, title, color in panels:
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

    fig.suptitle("Co-simulation Paper Highlight Metrics", fontsize=14)

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

    probe_df = pd.read_csv(input_dir / "cosim_invoke_probe.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "cosim_paper_highlight.csv", encoding="utf-8-sig")
    trace_df = pd.read_csv(input_dir / "external_environment_trace.csv", encoding="utf-8-sig")

    fig01_per_phase_impact(paper_df, output_dir)
    fig02_per_phase_invoke_events(paper_df, output_dir)
    fig03_cosim_timeline(probe_df, trace_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
