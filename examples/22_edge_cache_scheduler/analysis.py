"""
文件作用：edge_cache_scheduler 样例的结果导出与分析工具。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成调度策略摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            function_cache_hits=("function_cache_hit", "sum"),
            image_cache_hits=("image_cache_hit", "sum"),
            data_cache_hits=("data_cache_hit", "sum"),
            avg_estimated_latency=("estimated_latency", "mean"),
            total_estimated_latency=("estimated_latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            total_image_pull_penalty=("image_pull_penalty", "sum"),
            total_data_fetch_penalty=("data_fetch_penalty", "sum"),
        )
        .reset_index()
        .assign(
            function_cache_hit_rate=lambda df: df["function_cache_hits"] / df["request_count"],
            image_cache_hit_rate=lambda df: df["image_cache_hits"] / df["request_count"],
            data_cache_hit_rate=lambda df: df["data_cache_hits"] / df["request_count"],
        )
    )


def build_node_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成节点选择摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby(["policy_name", "selected_node"])
        .agg(
            request_count=("request_id", "count"),
            avg_estimated_latency=("estimated_latency", "mean"),
            function_cache_hits=("function_cache_hit", "sum"),
        )
        .reset_index()
    )


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成调度摘要。
    """
    result_df = outputs.get("edge_cache_scheduling_result", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame()

    return (
        result_df
        .groupby(["policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            function_cache_hit_rate=("function_cache_hit", "mean"),
            image_cache_hit_rate=("image_cache_hit", "mean"),
            data_cache_hit_rate=("data_cache_hit", "mean"),
            avg_estimated_latency=("estimated_latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
    )


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出调度实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = dict(outputs)
    outputs["edge_cache_policy_summary"] = build_policy_summary(outputs)
    outputs["edge_cache_node_summary"] = build_node_summary(outputs)
    outputs["edge_cache_function_summary"] = build_function_summary(outputs)

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
