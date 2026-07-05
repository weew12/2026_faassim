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

    重点统计 action_type=docker_pull 的网络传输事件。
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

    dfs["image_pull_summary"] = image_pull_summary_df
    dfs["image_pull_flow_summary"] = flow_summary_df

    return dfs
