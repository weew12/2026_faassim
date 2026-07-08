"""
文件作用：image_pull_network 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_size_vs_duration_scatter.png/pdf：镜像大小 vs 拉取耗时散点图
  论文 demo 关键图 —— 直观看出拉取时间随镜像大小线性增长
- fig02_deploy_phase_duration.png/pdf：3 个 pod 的 deploy 阶段总耗时柱状图
  按 deploy_to_finish_simtime 排序，cold/warm 视觉对比明显
- fig03_cold_warm_comparison.png/pdf：cold vs warm 缓存节省时间柱状图
  论文 demo 关键图 —— 同一镜像 cold 与 warm 的耗时差
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图

输入：05_image_pull_network/outputs/ 目录下的 CSV
输出：05_image_pull_network/figures/ 目录下的 png + pdf

运行：
    python -u examples/05_image_pull_network/plot.py
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
    "cold_pull": "#d62728",
    "warm_cache_hit": "#2ca02c",
}


def fig01_size_vs_duration_scatter(size_duration_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    散点图：镜像大小 vs 拉取耗时。
    """
    if size_duration_df.empty or "image_size_mb" not in size_duration_df.columns:
        logger.warning("size_duration_df is empty; skip fig01")
        return None

    df = size_duration_df.copy()
    # 排除 warm cache hit（duration=0）
    cold_df = df[df["pull_duration_seconds"] > 0].copy()
    warm_df = df[df["pull_duration_seconds"] <= 1e-9].copy()

    fig, ax = plt.subplots(figsize=(8, 4.5))

    # 冷拉取散点
    if not cold_df.empty:
        ax.scatter(cold_df["image_size_mb"], cold_df["pull_duration_seconds"],
                   s=200, c=SCENARIO_COLOR["cold_pull"], zorder=5,
                   edgecolors="black", linewidths=1.0, label="cold_pull")
        for _, row in cold_df.iterrows():
            ax.annotate(f"{row['image']}\n{row['function_name']}",
                        xy=(row["image_size_mb"], row["pull_duration_seconds"]),
                        xytext=(10, 10), textcoords="offset points",
                        fontsize=9, color="black")

    # warm cache hit（x轴上方加文本标记）
    if not warm_df.empty:
        for _, row in warm_df.iterrows():
            ax.scatter(row["image_size_mb"], 0,
                       s=200, c=SCENARIO_COLOR["warm_cache_hit"], zorder=5,
                       edgecolors="black", linewidths=1.0, marker="^")
            ax.annotate(f"{row['function_name']} (cache hit)",
                        xy=(row["image_size_mb"], 0),
                        xytext=(10, -25), textcoords="offset points",
                        fontsize=9, color=SCENARIO_COLOR["warm_cache_hit"])

    # 画理论拉取线：1000Mbps × 0.97 / 8 = 121.25 MB/s
    if not cold_df.empty:
        max_size = cold_df["image_size_mb"].max() * 1.2
        theoretical_sizes = np.array([0, max_size])
        theoretical_durations = theoretical_sizes / 121.25
        ax.plot(theoretical_sizes, theoretical_durations, color="gray",
                linestyle="--", linewidth=1.0, alpha=0.7,
                label="theoretical: 1Gbps × 0.97 / 8 ≈ 121 MB/s")

    ax.set_xlabel("Image Size (MB)")
    ax.set_ylabel("Pull Duration (s)")
    ax.set_title("Image Pull Duration vs Image Size (Skippy + docker.pull)")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=-0.1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")

    out = out_dir / "fig01_size_vs_duration_scatter"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_deploy_phase_duration(deploy_phase_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：3 个 pod 的 deploy 阶段总耗时（simtime-aware）。
    """
    if deploy_phase_df.empty or "deploy_to_finish_simtime" not in deploy_phase_df.columns:
        logger.warning("deploy_phase_df is empty; skip fig02")
        return None

    df = deploy_phase_df.copy().sort_values("deploy_to_finish_simtime", ascending=False).reset_index(drop=True)

    # 按 cold_or_warm 标色
    if "cache_hit_like" in df.columns:
        colors = [SCENARIO_COLOR["warm_cache_hit"] if c else SCENARIO_COLOR["cold_pull"]
                  for c in df["cache_hit_like"]]
    else:
        colors = ["#1f77b4"] * len(df)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(df["function_name"], df["deploy_to_finish_simtime"], color=colors)
    for bar, v, row in zip(bars, df["deploy_to_finish_simtime"], df.itertuples()):
        ipd = getattr(row, "image_pull_duration", 0.0)
        label = f"{v:.3f}s"
        if ipd > 0:
            label += f"\n(pull={ipd:.2f}s)"
        else:
            label += "\n(cache hit)"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                label, ha="center", va="bottom", fontsize=9)

    ax.set_title("Pod Deploy Phase Duration (simtime-aware)")
    ax.set_xlabel("Function")
    ax.set_ylabel("Deploy-to-Finish (simtime seconds)")
    ax.grid(True, axis="y", alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=SCENARIO_COLOR["cold_pull"], label="cold_pull"),
        Patch(facecolor=SCENARIO_COLOR["warm_cache_hit"], label="warm_cache_hit"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    out = out_dir / "fig02_deploy_phase_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_cold_warm_comparison(cold_warm_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    柱状图：cold vs warm cache 节省时间。
    """
    if cold_warm_df.empty or "cold_or_warm" not in cold_warm_df.columns:
        logger.warning("cold_warm_df is empty; skip fig03")
        return None

    df = cold_warm_df.copy()

    # 按 image 分组，每个 image 画 cold 和 warm 两个柱
    images = df["image"].unique().tolist()
    if not images:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(images))
    width = 0.35

    cold_durations = []
    warm_durations = []
    for img in images:
        cold_row = df[(df["image"] == img) & (df["cold_or_warm"] == "cold_pull")]
        warm_row = df[(df["image"] == img) & (df["cold_or_warm"] == "warm_cache_hit")]
        cold_durations.append(float(cold_row["avg_pull_duration"].iloc[0]) if len(cold_row) > 0 else 0.0)
        warm_durations.append(float(warm_row["avg_pull_duration"].iloc[0]) if len(warm_row) > 0 else 0.0)

    bars_cold = ax.bar(x - width / 2, cold_durations, width,
                       color=SCENARIO_COLOR["cold_pull"], label="cold_pull")
    bars_warm = ax.bar(x + width / 2, warm_durations, width,
                       color=SCENARIO_COLOR["warm_cache_hit"], label="warm_cache_hit")

    for bar, v in zip(bars_cold, cold_durations):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.3f}s", ha="center", va="bottom", fontsize=9)
    for bar, v in zip(bars_warm, warm_durations):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v:.3f}s", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels([img.replace("image-pull-", "").replace("-cpu", "") for img in images],
                       rotation=15, ha="right")
    ax.set_title("Cold vs Warm Cache Hit: pull duration comparison")
    ax.set_xlabel("Image")
    ax.set_ylabel("Avg Pull Duration (s)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")

    out = out_dir / "fig03_cold_warm_comparison"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画适合横向比较的耗时、速度和比例指标。镜像大小、flow 数和 invocation
    数保留在 CSV/README 中，不混入同一张图，避免尺度差异掩盖关键结论。
    """
    if paper_df.empty or "value" not in paper_df.columns or "metric" not in paper_df.columns:
        logger.warning("paper highlight df is empty; skip fig04")
        return None

    df = paper_df.copy()
    keep_metrics = [
        "small_cold_pull_duration_s",
        "small_warm_cache_hit_duration_s",
        "large_cold_pull_duration_s",
        "small_cold_pull_speed_mb_per_sec",
        "large_cold_pull_speed_mb_per_sec",
        "cache_savings_seconds",
        "cache_savings_ratio",
        "bandwidth_utilization_ratio",
        "invoke_probe_join_match_ratio",
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
    ax.set_title("Image Pull Network Paper Highlight Metrics")
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

    size_duration_df = pd.read_csv(input_dir / "image_pull_size_duration_comparison.csv", encoding="utf-8-sig")
    deploy_phase_df = pd.read_csv(input_dir / "image_pull_deploy_phase_duration.csv", encoding="utf-8-sig")
    cold_warm_df = pd.read_csv(input_dir / "image_pull_cold_warm_comparison.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "image_pull_paper_highlight.csv", encoding="utf-8-sig")

    fig01_size_vs_duration_scatter(size_duration_df, output_dir)
    fig02_deploy_phase_duration(deploy_phase_df, output_dir)
    fig03_cold_warm_comparison(cold_warm_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
