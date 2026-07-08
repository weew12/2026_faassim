"""
文件作用：cold_start 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_cold_start_path_gantt.png/pdf：
  冷启动路径阶段分解 Gantt 图（deploy/startup/setup/first_invoke/warm_invoke）。
  论文 demo 关键图 —— 一眼看出 cold_activation = deploy + startup + setup，
  first_request_path = cold_activation + first_invoke。
- fig02_first_vs_warm_compare.png/pdf：first_invoke vs warm_invoke 柱状图
  （3.75x speedup 是冷启动感知调度/预热策略的核心论点）。
- fig03_per_request_phase_duration.png/pdf：每次请求的 phase_duration
  散点（按 phase_start 排序），颜色按 phase；
  可直观看到 deploy 阶段受 docker.pull 实际拉取时间影响。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图。

输入：12_cold_start/outputs/ 目录下的 CSV
输出：12_cold_start/figures/ 目录下的 png + pdf

运行：
    python -u examples/12_cold_start/plot.py
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
    "deploy": "#1f77b4",
    "startup": "#ff7f0e",
    "setup": "#2ca02c",
    "first_invoke": "#d62728",
    "warm_invoke": "#9467bd",
}
PHASE_ORDER = ["deploy", "startup", "setup", "first_invoke", "warm_invoke"]


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
        description="Generate paper-demo figures for 12_cold_start.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/12_cold_start/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/12_cold_start/figures.",
    )
    return parser.parse_args()


def save_figure(fig, out: Path) -> None:
    """
    同时保存 png/pdf。
    """
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    logger.info("saved %s (.png/.pdf)", out)


def fig01_cold_start_path_gantt(probe_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    冷启动路径阶段分解 Gantt 图。

    - y 轴：5 个 phase（按顺序）
    - x 轴：simtime
    - 横向条：每个 phase 的 [phase_start, phase_finish] 区间
    """
    if probe_df.empty or "phase" not in probe_df.columns or "phase_start" not in probe_df.columns:
        logger.warning("cold_start_probe has no phase columns; skip fig01")
        return None

    df = probe_df.copy()
    df["phase_start"] = pd.to_numeric(df["phase_start"], errors="coerce")
    df["phase_finish"] = pd.to_numeric(df["phase_finish"], errors="coerce")
    df = df.dropna(subset=["phase_start", "phase_finish"])
    if df.empty:
        logger.warning("cold_start_probe has no valid phase_start/finish; skip fig01")
        return None

    fig, ax = plt.subplots(figsize=(10, 4.5))

    # 按 phase 顺序画 Gantt 条
    phase_to_y = {p: i for i, p in enumerate(reversed(PHASE_ORDER))}
    for _, row in df.iterrows():
        phase = str(row["phase"])
        if phase not in phase_to_y:
            continue
        y = phase_to_y[phase]
        start = float(row["phase_start"])
        finish = float(row["phase_finish"])
        duration = finish - start
        ax.barh(
            y,
            duration,
            left=start,
            color=PHASE_COLORS.get(phase, "#7f7f7f"),
            edgecolor="black",
            linewidth=0.5,
            height=0.6,
        )
        # 短条把文字放到右侧，长条放在条内部。
        label_inside = duration >= 0.25
        label_x = start + duration / 2 if label_inside else finish + 0.04
        ax.text(
            label_x,
            y,
            f"{duration:.2f}s",
            ha="center" if label_inside else "left",
            va="center",
            fontsize=8,
            color="white" if phase in ("deploy", "first_invoke") and label_inside else "black",
        )

    # 标出 cold_activation 范围（第一个 deploy.start → 最后一个 setup.finish）
    deploy_rows = df[df["phase"] == "deploy"]
    setup_rows = df[df["phase"] == "setup"]
    if not deploy_rows.empty and not setup_rows.empty:
        cold_start = float(deploy_rows["phase_start"].min())
        cold_end = float(setup_rows["phase_finish"].max())
        ax.axvspan(cold_start, cold_end, color="#1f77b4", alpha=0.06,
                   label="cold_activation")
        ax.axvline(cold_end, color="#1f77b4", linestyle="--", linewidth=1.0, alpha=0.6)

    ax.set_yticks(list(phase_to_y.values()))
    ax.set_yticklabels(list(phase_to_y.keys()))
    ax.set_xlabel("Simtime (s)")
    ax.set_title("Cold Start Path: Gantt of deploy + startup + setup + first/warm_invoke")
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    out = out_dir / "fig01_cold_start_path_gantt"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig02_first_vs_warm_compare(warm_cold_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    first_invoke vs warm_invoke 柱状图。

    论文 demo 关键图：3.75x speedup 是冷启动感知调度/预热策略的核心论点。
    """
    if warm_cold_df.empty or "phase" not in warm_cold_df.columns or "avg_invoke_duration" not in warm_cold_df.columns:
        logger.warning("warm_cold_compare is empty; skip fig02")
        return None

    df = warm_cold_df.copy()
    df["phase"] = df["phase"].astype(str)
    df = df[df["phase"].isin(["first_invoke", "warm_invoke"])].copy()
    if df.empty:
        logger.warning("no first/warm rows; skip fig02")
        return None

    # 按 first/warm 顺序
    df["__order__"] = df["phase"].apply(lambda p: 0 if p == "first_invoke" else 1)
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)

    first_avg = float(df[df["phase"] == "first_invoke"]["avg_invoke_duration"].iloc[0]) if (df["phase"] == "first_invoke").any() else 0.0
    warm_avg = float(df[df["phase"] == "warm_invoke"]["avg_invoke_duration"].iloc[0]) if (df["phase"] == "warm_invoke").any() else 0.0
    speedup = first_avg / warm_avg if warm_avg > 0 else 0.0

    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [PHASE_COLORS["first_invoke"], PHASE_COLORS["warm_invoke"]]
    bars = ax.bar(
        df["phase"],
        df["avg_invoke_duration"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars, df["avg_invoke_duration"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}s",
            ha="center",
            va="bottom",
        )

    ax.set_title(f"first_invoke vs warm_invoke ({speedup:.2f}x speedup)")
    ax.set_xlabel("Phase")
    ax.set_ylabel("avg_invoke_duration (s)")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_first_vs_warm_compare"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig03_per_request_phase_duration(probe_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    per-request phase_duration 散点图。

    - x 轴：phase_start simtime
    - y 轴：phase_duration
    - 颜色按 phase
    - 显示 deploy 受 docker.pull 拉取时间影响，其他 phase 是固定值
    """
    if probe_df.empty or "phase" not in probe_df.columns or "phase_duration" not in probe_df.columns:
        logger.warning("cold_start_probe has no phase columns; skip fig03")
        return None

    df = probe_df.copy()
    df["phase_start"] = pd.to_numeric(df["phase_start"], errors="coerce")
    df["phase_duration"] = pd.to_numeric(df["phase_duration"], errors="coerce")
    df = df.dropna(subset=["phase_start", "phase_duration"])
    if df.empty:
        logger.warning("cold_start_probe has no valid data; skip fig03")
        return None

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for phase in PHASE_ORDER:
        sub = df[df["phase"] == phase]
        if sub.empty:
            continue
        ax.scatter(
            sub["phase_start"],
            sub["phase_duration"],
            s=80,
            color=PHASE_COLORS.get(phase, "#7f7f7f"),
            edgecolors="black",
            linewidths=0.6,
            label=f"{phase} (n={len(sub)})",
            zorder=3,
        )

    # 标注固定值的水平参考线
    for phase, val in [
        ("startup", 0.75),
        ("setup", 0.55),
        ("first_invoke", 0.30),
        ("warm_invoke", 0.08),
    ]:
        ax.axhline(
            val,
            color=PHASE_COLORS[phase],
            linestyle=":",
            linewidth=0.9,
            alpha=0.55,
            label=f"{phase} reference = {val:.2f}s",
        )

    ax.set_title("Per-Phase phase_duration vs Simtime")
    ax.set_xlabel("phase_start (s)")
    ax.set_ylabel("phase_duration (s)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, ncol=2)

    out = out_dir / "fig03_per_request_phase_duration"
    save_figure(fig, out)
    plt.close(fig)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画数值型 metric（跳过 bool 型），便于一眼看出冷启动模型的关键数字。
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

    fig, ax = plt.subplots(figsize=(10, 6.5))
    bars = ax.barh(df["metric"], df["value_num"], color="#4c78a8")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}",
            ha="left",
            va="center",
        )
    ax.set_title("Cold Start Paper Highlight Metrics")
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

    probe_df = pd.read_csv(input_dir / "cold_start_probe.csv", encoding="utf-8-sig")
    warm_cold_df = pd.read_csv(input_dir / "cold_start_warm_cold_compare.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "cold_start_paper_highlight.csv", encoding="utf-8-sig")

    fig01_cold_start_path_gantt(probe_df, output_dir)
    fig02_first_vs_warm_compare(warm_cold_df, output_dir)
    fig03_per_request_phase_duration(probe_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
