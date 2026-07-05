"""
文件作用：cache_decision 样例的结果导出与分析工具。

该文件负责导出决策明细、策略摘要、容量排序和控制建议。
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd

from decision_model import CacheDecision, ControlHint

logger = logging.getLogger(__name__)


def decisions_to_dataframe(decisions: List[CacheDecision]) -> pd.DataFrame:
    """
    将缓存决策转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in decisions])


def hints_to_dataframe(hints: List[ControlHint]) -> pd.DataFrame:
    """
    将控制建议转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in hints])


def build_decision_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成决策摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["decision", "capacity_status"])
        .agg(
            function_count=("function_name", "count"),
            total_memory_units=("memory_units", "sum"),
            avg_utility_score=("utility_score", "mean"),
            max_utility_score=("utility_score", "max"),
        )
        .reset_index()
    )


def build_rank_table(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成容量选择排序表。
    """
    if decision_df.empty:
        return pd.DataFrame()

    rank_df = decision_df[
        decision_df["decision"].isin(["keep_warm", "prewarm_candidate"])
    ].copy()

    if rank_df.empty:
        return pd.DataFrame()

    rank_df = rank_df.sort_values("priority", ascending=False)
    rank_df["rank"] = range(1, len(rank_df) + 1)

    return rank_df[
        [
            "rank",
            "function_name",
            "decision",
            "memory_units",
            "utility_score",
            "priority",
            "capacity_status",
            "selected_by_budget",
            "reason",
        ]
    ]


def build_eviction_table(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成驱逐候选表。
    """
    if decision_df.empty:
        return pd.DataFrame()

    eviction_df = decision_df[decision_df["decision"] == "eviction_candidate"].copy()

    if eviction_df.empty:
        return pd.DataFrame()

    return eviction_df.sort_values("utility_score")[
        [
            "function_name",
            "current_replicas",
            "memory_units",
            "n_req",
            "last_seen_age",
            "in_flight_requests",
            "utility_score",
            "reason",
            "capacity_status",
        ]
    ]


def export_outputs(decisions: List[CacheDecision], hints: List[ControlHint], output_dir: Path):
    """
    导出缓存决策结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_df = decisions_to_dataframe(decisions)
    hint_df = hints_to_dataframe(hints)

    summary_df = build_decision_summary(decision_df)
    rank_df = build_rank_table(decision_df)
    eviction_df = build_eviction_table(decision_df)

    outputs = {
        "cache_decision_detail": decision_df,
        "cache_decision_summary": summary_df,
        "cache_decision_rank": rank_df,
        "cache_eviction_candidate": eviction_df,
        "cache_control_hint": hint_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
