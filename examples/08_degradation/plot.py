"""
文件作用：degradation 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_concurrency_vs_duration.png/pdf：并发数 vs 执行时间（含理论曲线）
  论文 demo 关键图 —— final = base * (1 + alpha * active) 线性退化
- fig02_concurrency_distribution.png/pdf：每个并发级别出现次数柱状图
  直观看出 18 rps 高并发率下不同负载级别的命中次数
- fig03_per_request_degradation.png/pdf：每条请求的 active_before 和 final_duration 时序
  直观看出 simulator 按请求顺序派发的退化情况
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：08_degradation/outputs/ 目录下的 CSV
输出：08_degradation/figures/ 目录下的 png + pdf

运行：
    python -u examples/08_degradation/plot.py
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


def fig01_concurrency_vs_duration(concurrency_df: pd.DataFrame, out_dir: Path, base_duration: float = 0.4, alpha: float = 0.35) -> Path:
    """
    并发数 vs 执行时间（含理论曲线）—— 论文 demo 关键图。
    """
    if concurrency_df.empty or "active_requests_before" not in concurrency_df.columns:
        logger.warning("concurrency_df is empty; skip fig01")
        return None

    df = concurrency_df.copy().sort_values("active_requests_before").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, 4.5))

    ax.plot(df["active_requests_before"], df["avg_final_duration"],
            "o-", color="#1f77b4", linewidth=1.5, markersize=8,
            label="avg final_duration")
    ax.plot(df["active_requests_before"], df["max_final_duration"],
            "s--", color="#ff7f0e", linewidth=1.0, markersize=6, alpha=0.7,
            label="max final_duration")

    # 理论曲线：final = base * (1 + alpha * active)
    xs = df["active_requests_before"].values
    ax.plot(xs, base_duration * (1 + alpha * xs),
            ":", color="grey", linewidth=2.0, alpha=0.7,
            label=f"theory: {base_duration} × (1 + {alpha} × active)")

    ax.set_xlabel("active_requests_before (concurrent load)")
    ax.set_ylabel("final_duration (simtime seconds)")
    ax.set_title("Degradation: request execution time vs node concurrent load")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    out = out_dir / "fig01_concurrency_vs_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_concurrency_distribution(concurrency_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：每个并发级别出现次数。
    """
    if concurrency_df.empty or "active_requests_before" not in concurrency_df.columns:
        logger.warning("concurrency_df is empty; skip fig02")
        return None

    df = concurrency_df.copy().sort_values("active_requests_before").reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    bars = ax.bar(df["active_requests_before"], df["request_count"],
                  color="#2ca02c", alpha=0.85)
    for bar, v in zip(bars, df["request_count"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{int(v)}", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("active_requests_before (concurrent load)")
    ax.set_ylabel("request count")
    ax.set_title("Degradation: how often each concurrency level was hit during the run")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_concurrency_distribution"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_per_request_degradation(probe_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    时序图：每条请求的 active_before 和 final_duration（按 request_id 排序）。
    """
    if probe_df.empty or "final_duration" not in probe_df.columns:
        logger.warning("probe_df is empty; skip fig03")
        return None

    df = probe_df.copy().sort_values("request_id").reset_index(drop=True)

    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)

    # 上图：active_requests_before
    ax = axes[0]
    ax.plot(df["request_id"], df["active_requests_before"],
            marker="o", markersize=5, linewidth=1.0, color="#1f77b4")
    ax.set_ylabel("active_requests_before")
    ax.set_title("Per-Request Degradation Timeline (sorted by request_id)")
    ax.grid(True, alpha=0.3)

    # 下图：final_duration
    ax = axes[1]
    ax.plot(df["request_id"], df["final_duration"],
            marker="s", markersize=5, linewidth=1.0, color="#d62728")
    ax.axhline(y=0.4, color="grey", linestyle="--", alpha=0.6, label="base_duration = 0.4s")
    ax.set_xlabel("request_id (chronological)")
    ax.set_ylabel("final_duration (simtime seconds)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    out = out_dir / "fig03_per_request_degradation"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画性能退化核心数值，跳过布尔和计数类指标，避免不同语义混在一张图里。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    df = paper_df.copy()
    keep_metrics = [
        "base_duration",
        "alpha",
        "max_degradation_factor",
        "max_final_duration",
        "avg_final_duration",
        "duration_match_ratio",
        "max_abs_diff",
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
    ax.set_title("Degradation Paper Highlight Metrics")
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

    concurrency_df = pd.read_csv(input_dir / "degradation_concurrency_distribution.csv", encoding="utf-8-sig")
    probe_df = pd.read_csv(input_dir / "degradation_probe.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "degradation_paper_highlight.csv", encoding="utf-8-sig")

    # base_duration 和 alpha 从 simulator 读出来 hardcode 与模型一致
    fig01_concurrency_vs_duration(concurrency_df, output_dir, base_duration=0.4, alpha=0.35)
    fig02_concurrency_distribution(concurrency_df, output_dir)
    fig03_per_request_degradation(probe_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
