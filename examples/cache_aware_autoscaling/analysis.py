"""
文件作用：cache_aware_autoscaling 样例的结果导出与分析工具。
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd

from models import AutoscalingDecision, ControlPlan

logger = logging.getLogger(__name__)


def decisions_to_dataframe(decisions: List[AutoscalingDecision]) -> pd.DataFrame:
    """
    将扩缩容决策转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in decisions])


def plans_to_dataframe(plans: List[ControlPlan]) -> pd.DataFrame:
    """
    将控制计划转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in plans])


def build_action_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成动作摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["action", "reason"])
        .agg(
            events=("function_name", "count"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            total_delta=("delta", "sum"),
        )
        .reset_index()
    )


def build_function_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    按函数生成摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby("function_name")
        .agg(
            records=("time", "count"),
            avg_cache_utility=("cache_utility", "mean"),
            max_r_cache=("r_cache", "max"),
            max_r_load=("r_load", "max"),
            max_r_desired=("r_desired", "max"),
            scale_out_events=("action", lambda s: int((s == "scale_out").sum())),
            scale_in_events=("action", lambda s: int((s == "scale_in").sum())),
            protect_events=("action", lambda s: int((s == "protect").sum())),
            prewarm_events=("action", lambda s: int((s == "prewarm").sum())),
        )
        .reset_index()
    )


def build_time_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    按时间生成总副本需求摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby("time")
        .agg(
            total_current_replicas=("current_replicas", "sum"),
            total_r_cache=("r_cache", "sum"),
            total_r_load=("r_load", "sum"),
            total_r_desired=("r_desired", "sum"),
            total_delta=("delta", "sum"),
            selected_cache_functions=("selected_by_cache_budget", "sum"),
        )
        .reset_index()
    )


def export_outputs(
    decisions: List[AutoscalingDecision],
    control_plans: List[ControlPlan],
    output_dir: Path,
):
    """
    导出扩缩容决策结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_df = decisions_to_dataframe(decisions)
    plan_df = plans_to_dataframe(control_plans)

    action_summary_df = build_action_summary(decision_df)
    function_summary_df = build_function_summary(decision_df)
    time_summary_df = build_time_summary(decision_df)

    outputs = {
        "cache_aware_autoscaling_decision": decision_df,
        "cache_aware_autoscaling_control_plan": plan_df,
        "cache_aware_autoscaling_action_summary": action_summary_df,
        "cache_aware_autoscaling_function_summary": function_summary_df,
        "cache_aware_autoscaling_time_summary": time_summary_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
