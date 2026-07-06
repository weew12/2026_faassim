"""
文件作用：batch_experiment 样例的单次实验指标导出和批量汇总分析。

该文件负责：
- 导出每个 run 的原始指标；
- 从原始指标中提取单行结果；
- 汇总所有 run 为 batch_results.csv；
- 按策略和负载聚合为 batch_summary.csv。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from experiment_config import ExperimentCase

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "batch_invoke_probe",
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


def export_case_outputs(sim, case: ExperimentCase, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出单个实验 case 的结果。
    """
    case_dir = output_dir / "runs" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = case_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    case_result_df = pd.DataFrame([build_case_result(case, dfs)])
    case_result_path = case_dir / "case_result.csv"
    case_result_df.to_csv(case_result_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", case_result_path)

    dfs["case_result"] = case_result_df
    return dfs


def build_case_result(case: ExperimentCase, dfs: Dict[str, pd.DataFrame]) -> Dict[str, object]:
    """
    从单次实验指标中提取单行结果。
    """
    probe_df = dfs.get("batch_invoke_probe", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    flow_df = dfs.get("flow", pd.DataFrame())

    result = {
        "case_id": case.case_id,
        "policy": case.policy.name,
        "scheduler": case.policy.scheduler,
        "workload": case.workload.name,
        "rps": case.workload.rps,
        "max_requests": case.workload.max_requests,
        "seed": case.seed,
        "probe_events": len(probe_df),
        "invocation_events": len(invocations_df),
        "schedule_events": len(schedule_df),
        "flow_events": len(flow_df),
    }

    if not probe_df.empty and "duration" in probe_df.columns:
        result["avg_probe_duration"] = float(probe_df["duration"].mean())
        result["max_probe_duration"] = float(probe_df["duration"].max())
        result["p95_probe_duration"] = float(probe_df["duration"].quantile(0.95))

    if not invocations_df.empty and "duration" in invocations_df.columns:
        result["avg_invocation_duration"] = float(invocations_df["duration"].mean())
        result["max_invocation_duration"] = float(invocations_df["duration"].max())

    if not schedule_df.empty and "node_name" in schedule_df.columns:
        result["scheduled_node_count"] = int(schedule_df["node_name"].dropna().nunique())

    if not flow_df.empty and "bytes" in flow_df.columns:
        result["flow_total_bytes"] = int(flow_df["bytes"].sum())

    return result


def export_batch_results(output_dir: Path, case_results: List[pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    导出批量实验总结果。
    """
    if case_results:
        batch_results_df = pd.concat(case_results, ignore_index=True)
    else:
        batch_results_df = pd.DataFrame()

    batch_results_path = output_dir / "batch_results.csv"
    batch_results_df.to_csv(batch_results_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", batch_results_path)

    batch_summary_df = build_batch_summary(batch_results_df)
    batch_summary_path = output_dir / "batch_summary.csv"
    batch_summary_df.to_csv(batch_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", batch_summary_path)

    return {
        "batch_results": batch_results_df,
        "batch_summary": batch_summary_df,
    }


def build_batch_summary(batch_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    按 policy 和 workload 汇总批量实验结果。
    """
    if batch_results_df.empty:
        return pd.DataFrame()

    agg_spec = {
        "runs": ("case_id", "count"),
        "avg_probe_events": ("probe_events", "mean"),
        "avg_invocation_events": ("invocation_events", "mean"),
    }

    if "avg_probe_duration" in batch_results_df.columns:
        agg_spec["mean_avg_probe_duration"] = ("avg_probe_duration", "mean")
        agg_spec["mean_p95_probe_duration"] = ("p95_probe_duration", "mean")

    if "flow_total_bytes" in batch_results_df.columns:
        agg_spec["avg_flow_total_bytes"] = ("flow_total_bytes", "mean")

    return (
        batch_results_df
        .groupby(["policy", "workload"])
        .agg(**agg_spec)
        .reset_index()
    )
