"""
文件作用：fault_model 样例的指标导出与简要分析工具。

该文件负责导出故障探针、故障时间线、调用、调度、资源和部署指标，
并生成请求成败摘要与故障类型分布。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "fault_model_probe",
    "fault_timeline",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
    "function_utilization",
    "node_utilization",
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


def build_fault_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成故障模型摘要。
    """
    probe_df = dfs.get("fault_model_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "request_events": 0,
            "success_count": 0,
            "failure_count": 0,
        }])

    success_count = int(probe_df["success"].sum()) if "success" in probe_df.columns else None
    failure_count = int((~probe_df["success"].astype(bool)).sum()) if "success" in probe_df.columns else None

    return pd.DataFrame([{
        "request_events": len(probe_df),
        "success_count": success_count,
        "failure_count": failure_count,
        "avg_final_duration": probe_df["final_duration"].mean() if "final_duration" in probe_df.columns else None,
        "max_final_duration": probe_df["final_duration"].max() if "final_duration" in probe_df.columns else None,
    }])


def build_fault_reason_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计不同故障原因的请求数量和平均耗时。
    """
    probe_df = dfs.get("fault_model_probe", pd.DataFrame())

    if probe_df.empty or "reason" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby(["reason", "success"])
        .agg(
            request_count=("final_duration", "count"),
            avg_final_duration=("final_duration", "mean"),
            max_final_duration=("final_duration", "max"),
        )
        .reset_index()
        .sort_values(["success", "request_count"], ascending=[True, False])
    )


def export_outputs(sim, output_dir: Path, fault_model) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    fault_event_df = fault_model.events_dataframe()
    fault_event_path = output_dir / "fault_events.csv"
    fault_event_df.to_csv(fault_event_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", fault_event_path)

    fault_summary_df = build_fault_summary(dfs)
    fault_summary_path = output_dir / "fault_model_summary.csv"
    fault_summary_df.to_csv(fault_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", fault_summary_path)

    fault_reason_df = build_fault_reason_distribution(dfs)
    fault_reason_path = output_dir / "fault_reason_distribution.csv"
    fault_reason_df.to_csv(fault_reason_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", fault_reason_path)

    dfs["fault_events"] = fault_event_df
    dfs["fault_model_summary"] = fault_summary_df
    dfs["fault_reason_distribution"] = fault_reason_df

    return dfs
