"""
文件作用：degradation 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取性能退化、调用、调度和部署指标，
并保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "degradation_probe",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
    "resource",
    "resources",
    "resource_monitor",
    "resource_state",
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


def build_degradation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成性能退化摘要。
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "degradation_events": 0,
        }])

    group_columns = [
        col for col in ["function_name", "node_name"]
        if col in probe_df.columns
    ]

    if not group_columns:
        return pd.DataFrame([{
            "degradation_events": len(probe_df),
            "avg_final_duration": probe_df["final_duration"].mean() if "final_duration" in probe_df.columns else None,
        }])

    return (
        probe_df
        .groupby(group_columns)
        .agg(
            degradation_events=("final_duration", "count"),
            avg_active_requests_before=("active_requests_before", "mean"),
            max_active_requests_before=("active_requests_before", "max"),
            avg_degradation_factor=("degradation_factor", "mean"),
            max_degradation_factor=("degradation_factor", "max"),
            avg_final_duration=("final_duration", "mean"),
            max_final_duration=("final_duration", "max"),
        )
        .reset_index()
    )


def build_concurrency_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计不同并发请求数下的执行时间分布。
    """
    probe_df = dfs.get("degradation_probe", pd.DataFrame())

    if probe_df.empty or "active_requests_before" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby("active_requests_before")
        .agg(
            request_count=("final_duration", "count"),
            avg_degradation_factor=("degradation_factor", "mean"),
            avg_final_duration=("final_duration", "mean"),
            min_final_duration=("final_duration", "min"),
            max_final_duration=("final_duration", "max"),
        )
        .reset_index()
        .sort_values("active_requests_before")
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

    degradation_summary_df = build_degradation_summary(dfs)
    degradation_summary_path = output_dir / "degradation_summary.csv"
    degradation_summary_df.to_csv(degradation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", degradation_summary_path)

    concurrency_distribution_df = build_concurrency_distribution(dfs)
    concurrency_distribution_path = output_dir / "degradation_concurrency_distribution.csv"
    concurrency_distribution_df.to_csv(concurrency_distribution_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", concurrency_distribution_path)

    dfs["degradation_summary"] = degradation_summary_df
    dfs["degradation_concurrency_distribution"] = concurrency_distribution_df

    return dfs
