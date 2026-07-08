"""
文件作用：负载均衡样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_routing_sequence_staircase.png/pdf：每次请求路由到哪个 replica 的阶梯图
  （论文 demo 关键图 —— 严格轮询应该呈现规律的 0,1,2,0,1,2,... 阶梯）
- fig02_replica_routing_distribution.png/pdf：每个 replica 收到的请求数（条形图）
- fig03_cumulative_replica_requests.png/pdf：每个 replica 的累计请求曲线
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：02_load_balancer/outputs/ 目录下的 CSV
输出：02_load_balancer/figures/ 目录下的 png + pdf

运行：
    python -u examples/02_load_balancer/plot.py
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
        description="Generate paper-demo figures for 02_load_balancer.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/02_load_balancer/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/02_load_balancer/figures.",
    )
    return parser.parse_args()


def fig01_routing_sequence_staircase(routing_seq_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    阶梯图：x=request_id, y=replica_index。

    严格轮询 LB 应该呈现规律的 0,1,2,0,1,2,... 阶梯。
    """
    if routing_seq_df.empty or "replica_index" not in routing_seq_df.columns:
        logger.warning("routing sequence is empty; skip fig01")
        return None

    df = routing_seq_df.sort_values("request_id") if "request_id" in routing_seq_df.columns else routing_seq_df.copy()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.step(
        df["request_id"] if "request_id" in df.columns else np.arange(len(df)),
        df["replica_index"],
        where="post",
        linewidth=1.5,
        color="#1f77b4",
    )
    ax.scatter(
        df["request_id"] if "request_id" in df.columns else np.arange(len(df)),
        df["replica_index"],
        s=20,
        color="#d62728",
        zorder=5,
    )
    ax.set_title("Round-Robin Routing Sequence (request_id -> replica_index)")
    ax.set_xlabel("Request ID (chronological)")
    ax.set_ylabel("Selected Replica Index")
    ax.set_yticks(sorted(df["replica_index"].unique()))
    ax.grid(True, alpha=0.3)

    out = out_dir / "fig01_routing_sequence_staircase"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_replica_routing_distribution(distribution_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    条形图：每个 replica 收到的请求数。
    """
    if distribution_df.empty or "routed_requests" not in distribution_df.columns:
        logger.warning("replica distribution is empty; skip fig02")
        return None

    df = distribution_df.copy()
    if "replica_index" in df.columns:
        df = df.sort_values("replica_index")
        df["label"] = df["replica_index"].apply(lambda x: f"replica {int(x)}")
    elif "selected_replica_id" in df.columns:
        df["label"] = df["selected_replica_id"].apply(lambda x: f"id ...{str(x)[-4:]}")
    else:
        df["label"] = [f"r{i}" for i in range(len(df))]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(df["label"], df["routed_requests"], color="#2ca02c")
    for bar, v in zip(bars, df["routed_requests"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(v)}",
                ha="center", va="bottom")
    ax.set_title("Per-Replica Routing Distribution")
    ax.set_xlabel("Replica")
    ax.set_ylabel("Routed Request Count")
    ax.grid(True, axis="y", alpha=0.3)

    out = out_dir / "fig02_replica_routing_distribution"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cumulative_replica_requests(routing_seq_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    折线图：每个 replica 随请求序号增长的累计路由次数。

    严格轮询下三条线应近似平行，最终都到 10。
    """
    if routing_seq_df.empty or "replica_index" not in routing_seq_df.columns:
        logger.warning("routing sequence has no replica_index; skip fig03")
        return None

    df = routing_seq_df.sort_values("request_id").reset_index(drop=True).copy()
    if "request_id" not in df.columns:
        df["request_id"] = np.arange(1, len(df) + 1)

    fig, ax = plt.subplots(figsize=(8, 4))
    for replica_index in sorted(df["replica_index"].unique()):
        mask = df["replica_index"] == replica_index
        cumulative = mask.astype(int).cumsum()
        ax.step(
            df["request_id"],
            cumulative,
            where="post",
            linewidth=2,
            label=f"replica {int(replica_index)}",
        )
    ax.set_title("Cumulative Routed Requests per Replica")
    ax.set_xlabel("Request ID")
    ax.set_ylabel("Cumulative Routed Requests")
    ax.set_ylim(0, max(df["replica_index"].value_counts().max() + 1, 2))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")

    out = out_dir / "fig03_cumulative_replica_requests"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画数值型 metric（跳过 bool 型 probe_*_match），
    便于一眼看出 round-robin LB 的关键数字。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    keep_metrics = [
        "route_events",
        "invocation_events",
        "selected_replica_count",
        "max_routed_requests",
        "min_routed_requests",
        "balance_std",
        "balance_ratio_min_over_max",
        "adjacent_switch_rate",
        "probe_invocation_t_exec_match_rate",
    ]
    df = paper_df[paper_df["metric"].isin(keep_metrics)].copy()
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value_num"])
    if df.empty:
        logger.warning("no numeric metrics in paper highlight; skip fig04")
        return None

    df = df.sort_values("value_num", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(df["metric"], df["value_num"], color="#4c78a8")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"{v:.4g}" if isinstance(v, float) and v != int(v) else f"{int(v)}",
                ha="left", va="center")
    ax.set_title("Load Balancer Paper Highlight Metrics")
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
    args = parse_args()
    input_dir, output_dir = args.input_dir, args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("input=%s output=%s", input_dir, output_dir)

    routing_seq_df = pd.read_csv(input_dir / "load_balancer_routing_sequence.csv", encoding="utf-8-sig")
    distribution_df = pd.read_csv(input_dir / "load_balancer_replica_distribution.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "load_balancer_paper_highlight.csv", encoding="utf-8-sig")

    fig01_routing_sequence_staircase(routing_seq_df, output_dir)
    fig02_replica_routing_distribution(distribution_df, output_dir)
    fig03_cumulative_replica_requests(routing_seq_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
