"""
文件作用：trace_oracle 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_trace_vs_invoke_duration.png/pdf：trace sample_duration vs inv_t_exec 双线对比
  论文 demo 关键图 —— 两条线完全重合 = oracle 行为正确
- fig02_sample_id_cycling.png/pdf：trace cursor 循环覆盖（fast 1→12→1→4，slow 1→12）
  论文 demo 关键图 —— 直观看出 fast 函数样本用完后从头循环
- fig03_per_function_duration.png/pdf：每个函数的 duration 分布（按 invoke_order）
  直观看出 trace 的 fast/slow 性能差异
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：07_trace_oracle/outputs/ 目录下的 CSV
输出：07_trace_oracle/figures/ 目录下的 png + pdf

运行：
    python -u examples/07_trace_oracle/plot.py
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
    "trace-fast-python-pi": "#1f77b4",
    "trace-slow-python-pi": "#ff7f0e",
}


def fig01_trace_vs_invoke_duration(join_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    双线对比图：trace sample_duration vs inv_t_exec（论文 demo 关键图）。

    两条线完全重合 = oracle 行为正确。
    """
    if join_df.empty or "sample_duration" not in join_df.columns:
        logger.warning("join_df is empty; skip fig01")
        return None

    df = join_df.copy()

    functions = sorted(df["function_name"].unique().tolist())
    n_cols = len(functions)
    fig, axes = plt.subplots(1, n_cols, figsize=(6 * n_cols, 4), sharey=False)

    if n_cols == 1:
        axes = [axes]

    for ax, fn in zip(axes, functions):
        sub = df[df["function_name"] == fn].sort_values("invoke_order").reset_index(drop=True)
        color = SCENARIO_COLOR.get(fn, "#7f7f7f")

        ax.plot(sub["invoke_order"], sub["sample_duration"],
                "o-", color=color, label="trace sample_duration",
                linewidth=1.5, markersize=6)
        ax.plot(sub["invoke_order"], sub["inv_t_exec"],
                "x--", color="black", label="invocation t_exec",
                linewidth=1.0, alpha=0.7, markersize=8)

        # 计算两条线 max diff
        max_diff = float((sub["sample_duration"] - sub["inv_t_exec"]).abs().max())

        ax.set_title(f"{fn}\nmax(|sample-t_exec|) = {max_diff:.2e}")
        ax.set_xlabel("invoke order")
        ax.set_ylabel("duration (simtime seconds)")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

    plt.suptitle("Trace sample vs invocation t_exec (overlap = oracle behavior is correct)")
    plt.tight_layout()

    out = out_dir / "fig01_trace_vs_invoke_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_sample_id_cycling(join_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    折线图：trace cursor 循环覆盖。

    fast 函数 16 次 invoke，trace 只有 12 个样本 → cursor 从 1→12 然后回到 1→4 停止
    slow 函数 12 次 invoke，恰好覆盖一个完整 cycle，不发生回卷
    """
    if join_df.empty or "sample_id" not in join_df.columns:
        logger.warning("join_df is empty; skip fig02")
        return None

    df = join_df.copy()

    fig, ax = plt.subplots(figsize=(10, 4.5))

    functions = sorted(df["function_name"].unique().tolist())
    offsets = np.linspace(-0.08, 0.08, num=len(functions)) if len(functions) > 1 else [0.0]

    for offset, fn in zip(offsets, functions):
        sub = df[df["function_name"] == fn].sort_values("invoke_order").reset_index(drop=True)
        color = SCENARIO_COLOR.get(fn, "#7f7f7f")
        x = sub["invoke_order"].astype(float) + offset
        ax.plot(x, sub["sample_id"], "o-",
                label=fn, color=color, linewidth=1.5, markersize=8)
        for _, row in sub.iterrows():
            ax.annotate(f"{int(row['sample_id'])}",
                        xy=(float(row["invoke_order"]) + offset, row["sample_id"]),
                        xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=7, color=color)

    # trace 长度参考线
    trace_length = 12
    ax.axhline(y=trace_length + 0.5, color="grey", linestyle=":", alpha=0.5,
               label=f"trace length ({trace_length})")
    ax.axhline(y=0.5, color="grey", linestyle="--", alpha=0.3)

    ax.set_xlabel("invoke order")
    ax.set_ylabel("trace sample_id")
    ax.set_title("Trace Cursor Cycling: fast wraps (12 -> 1 -> 4), slow completes one cycle")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    out = out_dir / "fig02_sample_id_cycling"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_per_function_duration(join_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：每个函数的 duration 分布（按 invoke_order）。
    """
    if join_df.empty or "sample_duration" not in join_df.columns:
        logger.warning("join_df is empty; skip fig03")
        return None

    df = join_df.copy()

    functions = sorted(df["function_name"].unique().tolist())
    n_cols = len(functions)
    fig, axes = plt.subplots(1, n_cols, figsize=(6 * n_cols, 4), sharey=False)

    if n_cols == 1:
        axes = [axes]

    for ax, fn in zip(axes, functions):
        sub = df[df["function_name"] == fn].sort_values("invoke_order").reset_index(drop=True)
        color = SCENARIO_COLOR.get(fn, "#7f7f7f")

        bars = ax.bar(sub["invoke_order"], sub["sample_duration"], color=color, alpha=0.85)
        for bar, v in zip(bars, sub["sample_duration"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v:.2f}", ha="center", va="bottom", fontsize=7)

        avg_d = float(sub["sample_duration"].mean())
        ax.axhline(y=avg_d, color="red", linestyle="--", linewidth=1.0, alpha=0.7,
                   label=f"avg = {avg_d:.3f}s")
        ax.set_title(f"{fn}\n(avg={avg_d:.3f}s, n={len(sub)})")
        ax.set_xlabel("invoke order")
        ax.set_ylabel("duration (simtime seconds)")
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)

    plt.suptitle("Per-Function Duration Distribution (from trace oracle)")
    plt.tight_layout()

    out = out_dir / "fig03_per_function_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画适合横向比较的比例、均值和循环指标。事件计数保留在
    trace_oracle_paper_highlight.csv 中，避免 28 这种计数压扁秒级指标。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    df = paper_df.copy()
    keep_metrics = [
        "duration_match_ratio",
        "probe_sample_match_ratio",
        "probe_invocation_match_ratio",
        "cycles_used_fast",
        "last_sample_id_fast",
        "fast_avg_duration_s",
        "slow_avg_duration_s",
    ]
    df = df[df["metric"].isin(keep_metrics)].copy()
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
    ax.set_title("Trace Oracle Paper Highlight Metrics")
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

    join_df = pd.read_csv(input_dir / "trace_invoke_sample_join.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "trace_oracle_paper_highlight.csv", encoding="utf-8-sig")

    fig01_trace_vs_invoke_duration(join_df, output_dir)
    fig02_sample_id_cycling(join_df, output_dir)
    fig03_per_function_duration(join_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
