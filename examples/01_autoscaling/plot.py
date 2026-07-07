"""
文件作用：01_autoscaling 样例的论文 demo 关键图生成脚本。

读 autoscaling_rps_replicas_timeline.csv + autoscaling_summary.csv +
autoscaling_paper_highlight.csv，画出 4 张论文 demo 关键图：

1. RPS vs Replicas 时间线（双 y 轴）
2. RPS 分布直方图
3. Replicas 时间线（柱状图）
4. 论文 demo 关键指标条形图（scale_up_factor、avg_rps_overall、peak_rps 等）

运行方式：
    python -u examples/01_autoscaling/plot.py

或者：
    python -u examples/01_autoscaling/plot.py --input-dir <outputs 目录> --output-dir <plots 目录>

输出：
    autoscaling_rps_vs_replicas.png
    autoscaling_rps_histogram.png
    autoscaling_replicas_timeline.png
    autoscaling_paper_highlight.png
    autoscaling_rps_vs_replicas.svg / .pdf （如有需要）
"""

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 离线画图（不需要 GUI）

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """配置日志输出。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def load_outputs(input_dir: Path) -> dict:
    """加载 outputs 目录下的所有 csv。"""
    files = {
        "timeline": "autoscaling_rps_replicas_timeline.csv",
        "summary": "autoscaling_summary.csv",
        "paper_highlight": "autoscaling_paper_highlight.csv",
        "probe_join": "autoscaling_probe_invocation_join.csv",
    }
    out = {}
    for key, filename in files.items():
        path = input_dir / filename
        if path.exists():
            out[key] = pd.read_csv(path, encoding="utf-8-sig")
            logger.info("loaded %s rows=%d", filename, len(out[key]))
        else:
            logger.warning("missing %s", filename)
            out[key] = pd.DataFrame()
    return out


def plot_rps_vs_replicas(timeline: pd.DataFrame, output_path: Path) -> None:
    """
    图 1：RPS vs Replicas 时间线（论文 demo 最核心的图）。

    双 y 轴：左轴 RPS（蓝色），右轴 Replicas（红色）。
    展示"负载上升 → 副本扩容 → 稳定" 的完整故事。
    """
    if timeline.empty:
        logger.warning("timeline empty, skip plot_rps_vs_replicas")
        return

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()

    # 左轴 RPS
    ax1.bar(
        timeline["simtime"],
        timeline["rps"],
        width=0.9,
        color="steelblue",
        alpha=0.6,
        label="RPS (1s window)",
    )
    ax1.set_xlabel("simtime (s)")
    ax1.set_ylabel("RPS (requests per second)", color="steelblue")
    ax1.tick_params(axis="y", labelcolor="steelblue")
    ax1.set_ylim(0, max(timeline["rps"].max() * 1.2, 1))

    # 右轴 Replicas（单调函数，画成 step 更直观）
    ax2.step(
        timeline["simtime"],
        timeline["replicas"],
        where="post",
        color="darkorange",
        linewidth=2.5,
        label="Replicas",
    )
    ax2.fill_between(
        timeline["simtime"],
        0,
        timeline["replicas"],
        step="post",
        color="darkorange",
        alpha=0.15,
    )
    ax2.set_ylabel("Replicas", color="darkorange")
    ax2.tick_params(axis="y", labelcolor="darkorange")
    ax2.set_ylim(0, max(timeline["replicas"].max() * 1.3, 2))

    # 标记 scale_up 事件
    if "invocation_count" in timeline.columns:
        peak_idx = timeline["rps"].idxmax()
        peak_simtime = float(timeline.loc[peak_idx, "simtime"])
        peak_rps = float(timeline.loc[peak_idx, "rps"])
        ax1.axvline(
            x=peak_simtime,
            color="red",
            linestyle="--",
            alpha=0.5,
            label=f"peak RPS ({peak_rps:.1f}) @ t={peak_simtime:.1f}s",
        )

    ax1.set_title("Autoscaling behavior under constant 40 RPS load\n(RPS vs Replicas timeline)")
    ax1.grid(True, alpha=0.3)

    # 合并图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (and .pdf)", output_path.name)


def plot_rps_histogram(timeline: pd.DataFrame, output_path: Path) -> None:
    """
    图 2：RPS 分布直方图。

    验证 RPS 是否稳定在 ~40（exponential arrival profile 的目标值）。
    """
    if timeline.empty or "rps" not in timeline.columns:
        logger.warning("timeline empty, skip plot_rps_histogram")
        return

    rps = timeline["rps"].dropna()
    rps_nonzero = rps[rps > 0]

    if len(rps_nonzero) == 0:
        logger.warning("no non-zero RPS, skip histogram")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(
        rps_nonzero,
        bins=20,
        color="steelblue",
        edgecolor="white",
        alpha=0.85,
    )
    ax.axvline(
        x=rps_nonzero.mean(),
        color="red",
        linestyle="--",
        label=f"mean = {rps_nonzero.mean():.1f} RPS",
    )
    ax.axvline(
        x=40.0,
        color="darkorange",
        linestyle=":",
        label="target = 40 RPS",
    )
    ax.set_xlabel("RPS (1s window)")
    ax.set_ylabel("window count")
    ax.set_title("RPS distribution across 1s windows")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", output_path.name)


def plot_replicas_timeline(timeline: pd.DataFrame, output_path: Path) -> None:
    """
    图 3：Replicas 时间线（柱状图）。

    更直观展示扩容时刻 + 副本数。
    """
    if timeline.empty or "replicas" not in timeline.columns:
        logger.warning("timeline empty, skip plot_replicas_timeline")
        return

    # 去重：只在 replicas 变化时画柱
    df = timeline[["simtime", "replicas"]].copy()
    df["prev_replicas"] = df["replicas"].shift(1).fillna(df["replicas"])
    changes = df[df["replicas"] != df["prev_replicas"]].copy()

    fig, ax = plt.subplots(figsize=(10, 4))
    # 用 step bar：每个 (change_simtime, replicas) 一个台阶
    ax.fill_between(
        df["simtime"],
        0,
        df["replicas"],
        step="post",
        color="darkorange",
        alpha=0.4,
    )
    ax.step(
        df["simtime"],
        df["replicas"],
        where="post",
        color="darkorange",
        linewidth=2.5,
        label="replicas",
    )
    # 标记 scale_up 时刻
    for _, row in changes.iterrows():
        direction = "up" if row["replicas"] > row["prev_replicas"] else "down"
        ax.axvline(
            x=row["simtime"],
            color="red",
            linestyle="--",
            alpha=0.7,
            label=(
                f"scale_{direction} to {int(row['replicas'])} @ t={row['simtime']:.2f}s"
            ),
        )

    ax.set_xlabel("simtime (s)")
    ax.set_ylabel("Replicas")
    ax.set_title("Replica count over time (autoscaling events)")
    ax.set_ylim(0, df["replicas"].max() * 1.2)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", output_path.name)


def plot_paper_highlight(paper_highlight: pd.DataFrame, output_path: Path) -> None:
    """
    图 4：论文 demo 关键指标条形图。

    把 paper_highlight 里的关键指标（scale_up_factor、avg_rps_overall、peak_rps、
    scale_up_response_time、probe_invocation_t_exec_match）画成条形图。
    """
    if paper_highlight.empty:
        logger.warning("paper_highlight empty, skip plot_paper_highlight")
        return

    # 选关键指标
    keep_metrics = [
        "scale_up_factor",
        "avg_rps_overall",
        "peak_rps",
        "scale_up_response_time",
        "probe_invocation_t_exec_match",
        "probe_invocation_simtime_match",
    ]
    df = paper_highlight[paper_highlight["metric"].isin(keep_metrics)].copy()

    if df.empty:
        logger.warning("no paper highlight metrics matched, skip")
        return

    df["value_float"] = df["value"].astype(float)
    df = df.sort_values("value_float", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["steelblue"] * len(df)
    ax.barh(
        df["metric"],
        df["value_float"],
        color=colors,
    )
    for i, v in enumerate(df["value_float"]):
        ax.text(v + max(df["value_float"]) * 0.01, i, f"{v:.3f}", va="center", fontsize=10)

    ax.set_xlabel("value")
    ax.set_title("Thesis paper highlight: autoscaling key metrics")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    fig.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s", output_path.name)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Generate thesis demo plots for 01_autoscaling.",
    )
    default_dir = Path(__file__).resolve().parent / "outputs"
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_dir,
        help="输入目录（包含 autoscaling_*.csv 的 outputs 目录）。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="图片输出目录（默认跟 input-dir 同目录下的 plots 子目录）。",
    )
    return parser.parse_args()


def main() -> None:
    """主入口。"""
    configure_logging()
    args = parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir or (input_dir / "plots")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("loading outputs from %s", input_dir)
    outputs = load_outputs(input_dir)

    if outputs["timeline"].empty:
        logger.error("timeline is empty, please run main.py first")
        sys.exit(1)

    logger.info("generating 4 plots into %s", output_dir)
    plot_rps_vs_replicas(outputs["timeline"], output_dir / "autoscaling_rps_vs_replicas.png")
    plot_rps_histogram(outputs["timeline"], output_dir / "autoscaling_rps_histogram.png")
    plot_replicas_timeline(outputs["timeline"], output_dir / "autoscaling_replicas_timeline.png")
    plot_paper_highlight(outputs["paper_highlight"], output_dir / "autoscaling_paper_highlight.png")

    logger.info("all plots saved to %s", output_dir)
    for png in sorted(output_dir.glob("*.png")):
        size_kb = png.stat().st_size / 1024
        logger.info("  %s (%.1f KB)", png.name, size_kb)


if __name__ == "__main__":
    main()
