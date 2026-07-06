"""
文件作用：resource_monitor 样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取资源监控、调用、部署和网络流相关指标，
并保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


# 不同 faas-sim 版本中资源监控指标名称可能略有差异。
# 因此这里同时尝试多个常见名称，缺失的指标会被安全跳过。
METRIC_NAMES = [
    "function_utilization",
    "node_utilization",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
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


def find_resource_dataframe(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    从候选指标中选一个非空的资源监控 DataFrame。
    """
    for name in ["function_utilization", "node_utilization"]:
        df = dfs.get(name, pd.DataFrame())
        if not df.empty:
            return df
    return pd.DataFrame()


def build_resource_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成资源监控摘要。

    由于不同版本的资源指标列名可能不同，本函数采用兼容式处理：
    - 如果存在 value 列，则统计 value 的均值和最大值；
    - 如果存在 resource / resource_name 列，则按资源类型分组；
    - 如果存在 node_name 列，则按节点分组。
    """
    resource_df = find_resource_dataframe(dfs)

    if resource_df.empty:
        return pd.DataFrame([{
            "resource_metric_events": 0,
            "message": "no resource monitor dataframe found",
        }])

    group_columns = []

    for col in ["node_name", "resource", "resource_name", "name"]:
        if col in resource_df.columns:
            group_columns.append(col)

    value_col = None
    for col in ["value", "amount", "usage", "cpu", "memory"]:
        if col in resource_df.columns:
            value_col = col
            break

    if group_columns and value_col:
        return (
            resource_df
            .groupby(group_columns)
            .agg(
                samples=(value_col, "count"),
                avg_value=(value_col, "mean"),
                max_value=(value_col, "max"),
            )
            .reset_index()
        )

    return pd.DataFrame([{
        "resource_metric_events": len(resource_df),
        "columns": ",".join(resource_df.columns.astype(str).tolist()),
    }])


def build_invocation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成调用摘要。
    """
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if invocations_df.empty:
        return pd.DataFrame([{
            "invocation_events": 0,
        }])

    result = {
        "invocation_events": len(invocations_df),
    }

    if "function_name" in invocations_df.columns:
        result["function_count"] = invocations_df["function_name"].nunique()

    if "duration" in invocations_df.columns:
        result["avg_duration"] = invocations_df["duration"].mean()
        result["max_duration"] = invocations_df["duration"].max()

    return pd.DataFrame([result])


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

    resource_summary_df = build_resource_summary(dfs)
    resource_summary_path = output_dir / "resource_monitor_summary.csv"
    resource_summary_df.to_csv(resource_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", resource_summary_path)

    invocation_summary_df = build_invocation_summary(dfs)
    invocation_summary_path = output_dir / "resource_monitor_invocation_summary.csv"
    invocation_summary_df.to_csv(invocation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invocation_summary_path)

    dfs["resource_monitor_summary"] = resource_summary_df
    dfs["resource_monitor_invocation_summary"] = invocation_summary_df

    return dfs
