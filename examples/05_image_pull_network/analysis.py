"""
文件作用：image_pull_network 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取镜像拉取、网络流、部署生命周期等指标，
并保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "image_pull_probe",
    "flow",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
]


def extract_metrics(sim) -> Dict[str, pd.DataFrame]:
    """
    从仿真对象中提取常用指标。
    """
    dfs: Dict[str, pd.DataFrame] = {}

    for name in METRIC_NAMES:
        try:
            df = sim.env.metrics.extract_dataframe(name)
            dfs[name] = df
            logger.info("metric %s extracted, rows=%d", name, len(df))
        except Exception as err:
            logger.warning("metric %s not available: %s", name, err)
            dfs[name] = pd.DataFrame()

    return dfs


def build_image_pull_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成镜像拉取摘要。

    摘要按 function_name、image、node_name 分组，统计：
    - 拉取次数；
    - 平均拉取耗时；
    - 最大拉取耗时；
    - 近似缓存命中次数。
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame()

    group_columns = [
        col for col in ["function_name", "image", "node_name"]
        if col in probe_df.columns
    ]

    if not group_columns:
        return probe_df

    return (
        probe_df
        .groupby(group_columns)
        .agg(
            pull_events=("image_pull_duration", "count"),
            avg_pull_duration=("image_pull_duration", "mean"),
            max_pull_duration=("image_pull_duration", "max"),
            cache_hit_like_count=("cache_hit_like", "sum"),
        )
        .reset_index()
    )


def build_flow_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成网络 Flow 摘要。

    按 action_type × source × sink 分组，统计 docker_pull 等网络传输事件。
    flow.csv 不含 image 列，所以这里的分组不包含 image。
    如需按 image 拆分的拉取对比，请使用 image_pull_cold_warm_comparison.csv。
    """
    flow_df = dfs.get("flow", pd.DataFrame())

    if flow_df.empty:
        return pd.DataFrame()

    group_columns = [
        col for col in ["action_type", "source", "sink"]
        if col in flow_df.columns
    ]

    if not group_columns:
        return flow_df

    return (
        flow_df
        .groupby(group_columns)
        .agg(
            flow_count=("bytes", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
            max_duration=("duration", "max"),
        )
        .reset_index()
        .sort_values(["action_type", "source"], ascending=[True, True])
    )


def build_cold_warm_comparison(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成冷/热拉取对比摘要。

    按 (image, cold_or_warm) 维度汇总 image_pull_probe 数据：
    - cold：首次拉取，duration > 0
    - warm：缓存命中，duration == 0

    这是论文里最直观的"小镜像冷拉 vs 热复用"对比图的数据源。
    """
    probe_df = dfs.get("image_pull_probe", pd.DataFrame())

    if probe_df.empty or "image_pull_duration" not in probe_df.columns:
        return pd.DataFrame()

    work_df = probe_df.copy()
    work_df["cold_or_warm"] = work_df["cache_hit_like"].map(
        {True: "warm_cache_hit", False: "cold_pull"}
    ).fillna("unknown")

    group_columns = ["image", "cold_or_warm"]
    available = [c for c in group_columns if c in work_df.columns]
    if not available:
        return pd.DataFrame()

    return (
        work_df
        .groupby(available)
        .agg(
            pull_events=("image_pull_duration", "count"),
            avg_pull_duration=("image_pull_duration", "mean"),
            min_pull_duration=("image_pull_duration", "min"),
            max_pull_duration=("image_pull_duration", "max"),
        )
        .reset_index()
        .sort_values(["image", "cold_or_warm"], ascending=[True, True])
    )


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    image_pull_summary_df = build_image_pull_summary(dfs)
    image_pull_summary_path = output_dir / "image_pull_summary.csv"
    image_pull_summary_df.to_csv(image_pull_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", image_pull_summary_path)

    flow_summary_df = build_flow_summary(dfs)
    flow_summary_path = output_dir / "image_pull_flow_summary.csv"
    flow_summary_df.to_csv(flow_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", flow_summary_path)

    cold_warm_df = build_cold_warm_comparison(dfs)
    cold_warm_path = output_dir / "image_pull_cold_warm_comparison.csv"
    cold_warm_df.to_csv(cold_warm_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", cold_warm_path)

    dfs["image_pull_summary"] = image_pull_summary_df
    dfs["image_pull_flow_summary"] = flow_summary_df
    dfs["image_pull_cold_warm_comparison"] = cold_warm_df

    return dfs
