"""
文件作用：cache_policy 样例的结果导出与分析工具。

该文件负责导出请求结果、驱逐事件、缓存状态和策略对比摘要。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据请求级结果生成策略摘要。
    """
    request_df = outputs.get("cache_request_result", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    return (
        request_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            max_latency=("latency", "max"),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_cache_used_after=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(hit_rate=lambda df: df["hit_count"] / df["request_count"])
    )


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按策略和函数生成摘要。
    """
    request_df = outputs.get("cache_request_result", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    return (
        request_df
        .groupby(["policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
        .assign(hit_rate=lambda df: df["hit_count"] / df["request_count"])
    )


def build_eviction_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成驱逐摘要。
    """
    eviction_df = outputs.get("cache_eviction", pd.DataFrame())

    if eviction_df.empty:
        return pd.DataFrame([{
            "policy_name": "none",
            "eviction_count": 0,
        }])

    return (
        eviction_df
        .groupby(["policy_name", "reason"])
        .agg(
            eviction_count=("evicted_function", "count"),
            avg_score=("score", "mean"),
        )
        .reset_index()
    )


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出缓存策略实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_summary_df = build_policy_summary(outputs)
    function_summary_df = build_function_summary(outputs)
    eviction_summary_df = build_eviction_summary(outputs)

    outputs = dict(outputs)
    outputs["cache_policy_summary"] = policy_summary_df
    outputs["cache_function_summary"] = function_summary_df
    outputs["cache_eviction_summary"] = eviction_summary_df

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
