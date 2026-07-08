"""
文件作用：image_cache 样例的绘图脚本。

4 张图（沿用 01-23 的 plot 模式：png+pdf 同时输出）：
- fig01_cache_effect_comparison.png/pdf：
  同节点缓存复用 vs 不同节点冷拉取 的总耗时 + 网络流量对比柱状图。
  论文 demo 关键图 —— 视觉证明 2.0x speedup + 128MB 流量节省。
- fig02_per_deploy_pull_duration.png/pdf：
  每次部署的 pull_duration 散点（按 simtime 排序），颜色按 cache_hit_before；
  same_node 第二点 cache_hit_before=True 的 pull_duration ≈ 0。
- fig03_node_cache_state_evolution.png/pdf：
  各节点在不同部署步骤后的 cached_image_count_after 阶梯图，
  same_node 始终在 server_0，different_node 分别在 server_0/server_1。
- fig04_paper_highlight_metrics.png/pdf：论文 demo 关键摘要指标条形图。

输入：13_image_cache/outputs/ 目录下的 CSV
输出：13_image_cache/figures/ 目录下的 png + pdf

运行：
    python -u examples/13_image_cache/plot.py
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


SCENARIO_COLORS = {
    "same_node_cache_reuse": "#2ca02c",
    "different_node_cold_pull": "#d62728",
}
SCENARIO_ORDER = ["same_node_cache_reuse", "different_node_cold_pull"]


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
        description="Generate paper-demo figures for 13_image_cache.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=here / "outputs",
        help="CSV input directory. Defaults to examples/13_image_cache/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=here / "figures",
        help="Figure output directory. Defaults to examples/13_image_cache/figures.",
    )
    return parser.parse_args()


def fig01_cache_effect_comparison(comparison_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    同节点缓存复用 vs 不同节点冷拉取 的总耗时 + 网络流量对比柱状图。

    论文 demo 关键图：2.0x speedup + 128MB 流量节省。
    """
    if comparison_df.empty or "scenario" not in comparison_df.columns:
        logger.warning("comparison is empty; skip fig01")
        return None

    df = comparison_df.copy()
    df["__order__"] = df["scenario"].apply(
        lambda s: SCENARIO_ORDER.index(s) if s in SCENARIO_ORDER else len(SCENARIO_ORDER)
    )
    df = df.sort_values("__order__").drop(columns="__order__").reset_index(drop=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    # 左：total_pull_duration
    colors = [SCENARIO_COLORS.get(s, "#7f7f7f") for s in df["scenario"]]
    bars1 = ax1.bar(
        df["scenario"],
        df["total_pull_duration"],
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars1, df["total_pull_duration"]):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.2f}s",
            ha="center",
            va="bottom",
        )
    ax1.set_title("Total docker.pull duration (s)")
    ax1.set_ylabel("seconds")
    ax1.grid(True, axis="y", alpha=0.3)

    # 右：docker_pull_bytes (MB)
    bytes_mb = df["docker_pull_total_bytes"] / 1e6
    bars2 = ax2.bar(
        df["scenario"],
        bytes_mb,
        color=colors,
        edgecolor="black",
        linewidth=0.5,
    )
    for bar, v in zip(bars2, bytes_mb):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{v:.0f}MB",
            ha="center",
            va="bottom",
        )
    ax2.set_title("docker.pull network bytes (MB)")
    ax2.set_ylabel("MB")
    ax2.grid(True, axis="y", alpha=0.3)

    # 旋转 x 轴标签
    for ax in (ax1, ax2):
        ax.tick_params(axis="x", rotation=15)

    # 整体标题：speedup
    speedup = 0.0
    reuse_row = df[df["scenario"] == "same_node_cache_reuse"]
    cold_row = df[df["scenario"] == "different_node_cold_pull"]
    if not reuse_row.empty and not cold_row.empty:
        rt = float(reuse_row["total_pull_duration"].iloc[0])
        ct = float(cold_row["total_pull_duration"].iloc[0])
        speedup = ct / rt if rt > 0 else 0.0

    fig.suptitle(f"Image Cache Effect: same_node vs different_node ({speedup:.2f}x speedup)", fontsize=12)
    plt.tight_layout()

    out = out_dir / "fig01_cache_effect_comparison"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig02_per_deploy_pull_duration(
    same_node_probe_df: pd.DataFrame,
    different_node_probe_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    每次部署的 pull_duration 散点（按 simtime 排序），颜色按 cache_hit_before。

    same_node 第二点 cache_hit_before=True 的 pull_duration ≈ 0。
    """
    if same_node_probe_df.empty or different_node_probe_df.empty:
        logger.warning("probe df is empty; skip fig02")
        return None

    # faas-sim 的 simtime 不在 probe 里直接给，用 deploy 序号作 x 轴。
    # 这里的 x 是 scenario 内绝对 deploy 序号（每个场景有 2 次部署）。
    # 同一场景的 2 个点用相同 x 范围（1, 2），但 different_node 向右偏移 0.5 避免重叠。
    fig, ax = plt.subplots(figsize=(10, 4.5))

    x_offset_by_scenario = {
        "same_node_cache_reuse": 0.0,
        "different_node_cold_pull": 0.5,
    }

    for scenario, probe_df, color in [
        ("same_node_cache_reuse", same_node_probe_df, SCENARIO_COLORS["same_node_cache_reuse"]),
        ("different_node_cold_pull", different_node_probe_df, SCENARIO_COLORS["different_node_cold_pull"]),
    ]:
        df = probe_df.copy()
        if "pull_duration" not in df.columns:
            continue
        df["pull_duration"] = pd.to_numeric(df["pull_duration"], errors="coerce")
        if "cache_hit_before" in df.columns:
            df["cache_hit_before"] = df["cache_hit_before"].astype(bool)
        df = df.reset_index(drop=True)

        x_offset = x_offset_by_scenario[scenario]
        for i, row in df.iterrows():
            hit = bool(row.get("cache_hit_before")) if "cache_hit_before" in df.columns else False
            marker = "o" if hit else "^"
            label = (
                f"{scenario} (cache_hit_before={hit})"
                if i == 0
                else None
            )
            ax.scatter(
                i + 1 + x_offset,
                float(row["pull_duration"]),
                s=200,
                color=color,
                edgecolors="black",
                linewidths=1.0,
                marker=marker,
                label=label,
                zorder=5,
            )
            ax.annotate(
                f"{float(row['pull_duration']):.3f}s (hit={hit})",
                (i + 1 + x_offset, float(row["pull_duration"])),
                textcoords="offset points",
                xytext=(10, 8),
                fontsize=8,
                color="black",
            )

    ax.set_title("Per-Deploy pull_duration (same_node vs different_node)")
    ax.set_xlabel("Deploy sequence (within scenario)")
    ax.set_ylabel("pull_duration (s)")
    ax.set_xticks([1, 1.5, 2, 2.5])
    ax.set_xticklabels(["1\n(same)", "1\n(diff)", "2\n(same)", "2\n(diff)"])
    ax.set_xlim(0.4, 3.0)
    ax.set_ylim(-0.5, 7.0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=8, ncol=1, framealpha=0.9)

    out = out_dir / "fig02_per_deploy_pull_duration"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig03_node_cache_state_evolution(
    same_node_probe_df: pd.DataFrame,
    different_node_probe_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    """
    各节点在不同部署步骤后的 cached_image_count_after 阶梯图。

    same_node: server_0 始终，cached_image_count_after 从 0 → 1 → 1。
    different_node: server_0 和 server_1 各走一遍，各从 0 → 1。
    """
    if same_node_probe_df.empty or different_node_probe_df.empty:
        logger.warning("probe df is empty; skip fig03")
        return None

    fig, ax = plt.subplots(figsize=(10, 4.5))
    line_styles = {
        "server_0": "-",
        "server_1": "--",
    }

    for scenario, probe_df, color in [
        ("same_node_cache_reuse", same_node_probe_df, SCENARIO_COLORS["same_node_cache_reuse"]),
        ("different_node_cold_pull", different_node_probe_df, SCENARIO_COLORS["different_node_cold_pull"]),
    ]:
        df = probe_df.copy()
        if "cached_image_count_after" not in df.columns or "node_name" not in df.columns:
            continue
        df["cached_image_count_after"] = pd.to_numeric(df["cached_image_count_after"], errors="coerce")
        df["cached_image_count_before"] = pd.to_numeric(
            df.get("cached_image_count_before", 0),
            errors="coerce",
        ).fillna(0)
        df["deploy_step"] = np.arange(1, len(df) + 1)
        for node_name, sub in df.groupby("node_name", dropna=False):
            if sub.empty:
                continue
            sub_sorted = sub.sort_values("deploy_step").reset_index(drop=True)
            x_vals = np.concatenate(([0], sub_sorted["deploy_step"].to_numpy(dtype=float)))
            y_vals = np.concatenate((
                [float(sub_sorted["cached_image_count_before"].iloc[0])],
                sub_sorted["cached_image_count_after"].to_numpy(dtype=float),
            ))
            label = f"{scenario}/{node_name}"
            ax.step(
                x_vals,
                y_vals,
                where="post",
                linewidth=2.0,
                color=color,
                linestyle=line_styles.get(str(node_name), "-"),
                label=label,
            )
            ax.scatter(
                x_vals,
                y_vals,
                s=60,
                color=color,
                edgecolors="black",
                linewidths=0.4,
                zorder=3,
            )

    ax.set_title("Node-level cached_image_count_after over deploys")
    ax.set_xlabel("Global deploy sequence (within scenario)")
    ax.set_ylabel("cached_image_count_after")
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["start", "deploy 1", "deploy 2"])
    ax.set_yticks([0, 1, 2])
    ax.set_ylim(-0.2, 2.2)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    out = out_dir / "fig03_node_cache_state_evolution"
    for ext in FIGURE_FORMAT:
        fig.savefig(out.with_suffix(f".{ext}"), dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("saved %s (.png/.pdf)", out)
    return out


def fig04_paper_highlight_metrics(paper_df: pd.DataFrame, out_dir: Path) -> Path:
    """
    论文 demo 关键摘要指标条形图。

    只画数值型 metric，便于一眼看出镜像缓存的关键数字。
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

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(df["metric"], df["value_num"], color="#4c78a8")
    for bar, v in zip(bars, df["value_num"]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"{v:.4g}" if (isinstance(v, float) and abs(v - int(v)) > 1e-9) else f"{int(v)}",
            ha="left",
            va="center",
        )
    ax.set_title("Image Cache Paper Highlight Metrics")
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

    comparison_df = pd.read_csv(input_dir / "image_cache_comparison.csv", encoding="utf-8-sig")
    paper_df = pd.read_csv(input_dir / "image_cache_paper_highlight.csv", encoding="utf-8-sig")
    same_node_probe_df = pd.read_csv(
        input_dir / "same_node_cache_reuse" / "image_cache_probe.csv",
        encoding="utf-8-sig",
    )
    different_node_probe_df = pd.read_csv(
        input_dir / "different_node_cold_pull" / "image_cache_probe.csv",
        encoding="utf-8-sig",
    )

    fig01_cache_effect_comparison(comparison_df, output_dir)
    fig02_per_deploy_pull_duration(same_node_probe_df, different_node_probe_df, output_dir)
    fig03_node_cache_state_evolution(same_node_probe_df, different_node_probe_df, output_dir)
    fig04_paper_highlight_metrics(paper_df, output_dir)

    logger.info("done.")


if __name__ == "__main__":
    main()
