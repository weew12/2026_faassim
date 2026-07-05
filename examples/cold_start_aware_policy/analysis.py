"""
文件作用：cold_start_aware_policy 样例的结果导出与分析工具。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略摘要。
    """
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())
    eviction_df = outputs.get("cold_start_eviction", pd.DataFrame())

    if request_df.empty:
        return pd.DataFrame()

    summary = (
        request_df
        .groupby("policy_name")
        .agg(
            request_count=("request_id", "count"),
            hit_count=("cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            max_latency=("latency", "max"),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_keep_alive_window=("keep_alive_window", "mean"),
            avg_cache_used=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(hit_rate=lambda df: df["hit_count"] / df["request_count"])
    )

    if not eviction_df.empty:
        eviction_summary = (
            eviction_df
            .groupby("policy_name")
            .agg(eviction_count=("evicted_function", "count"))
            .reset_index()
        )
        summary = summary.merge(eviction_summary, on="policy_name", how="left")
    else:
        summary["eviction_count"] = 0

    summary["eviction_count"] = summary["eviction_count"].fillna(0).astype(int)
    return summary


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成策略结果摘要。
    """
    request_df = outputs.get("cold_start_request_result", pd.DataFrame())

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
            avg_keep_alive_window=("keep_alive_window", "mean"),
        )
        .reset_index()
        .assign(hit_rate=lambda df: df["hit_count"] / df["request_count"])
    )


def build_decision_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略决策摘要。
    """
    decision_df = outputs.get("cold_start_policy_decision", pd.DataFrame())

    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["policy_name", "decision", "reason"])
        .agg(
            events=("request_id", "count"),
            avg_utility=("utility", "mean"),
            avg_keep_alive_window=("keep_alive_window", "mean"),
        )
        .reset_index()
    )


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出策略实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = dict(outputs)
    outputs["cold_start_policy_summary"] = build_policy_summary(outputs)
    outputs["cold_start_function_summary"] = build_function_summary(outputs)
    outputs["cold_start_decision_summary"] = build_decision_summary(outputs)

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
