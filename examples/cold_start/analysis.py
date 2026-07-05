"""
文件作用：cold_start 样例的指标导出与分析工具。

该文件负责从 sim.env.metrics 中提取冷启动阶段、调用、部署、调度和网络流指标，
并生成冷启动路径摘要、阶段耗时摘要和 warm/cold 调用对比。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cold_start_probe",
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


def build_phase_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成各阶段耗时摘要。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "phase_events": 0,
        }])

    if "phase" not in probe_df.columns or "phase_duration" not in probe_df.columns:
        return pd.DataFrame([{
            "phase_events": len(probe_df),
            "columns": ",".join(probe_df.columns.astype(str).tolist()),
        }])

    return (
        probe_df
        .groupby("phase")
        .agg(
            events=("phase_duration", "count"),
            avg_duration=("phase_duration", "mean"),
            min_duration=("phase_duration", "min"),
            max_duration=("phase_duration", "max"),
        )
        .reset_index()
    )


def build_replica_cold_path_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按副本汇总冷启动路径。

    冷启动路径定义为 deploy + startup + setup。
    first_invoke 单独列出，用于分析首次请求开销。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty or "replica_id" not in probe_df.columns:
        return pd.DataFrame()

    rows = []

    for replica_id, group in probe_df.groupby("replica_id"):
        row = {
            "replica_id": replica_id,
            "function_name": group["function_name"].iloc[0] if "function_name" in group.columns else None,
            "node_name": group["node_name"].iloc[0] if "node_name" in group.columns else None,
        }

        for phase in ["deploy", "startup", "setup", "first_invoke", "warm_invoke"]:
            phase_group = group[group["phase"] == phase] if "phase" in group.columns else pd.DataFrame()
            row[f"{phase}_events"] = len(phase_group)
            row[f"{phase}_total_duration"] = (
                float(phase_group["phase_duration"].sum())
                if not phase_group.empty and "phase_duration" in phase_group.columns
                else 0.0
            )

        row["cold_activation_duration"] = (
            row["deploy_total_duration"]
            + row["startup_total_duration"]
            + row["setup_total_duration"]
        )
        row["first_request_path_duration"] = (
            row["cold_activation_duration"]
            + row["first_invoke_total_duration"]
        )

        rows.append(row)

    return pd.DataFrame(rows)


def build_warm_cold_compare(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    对比 first_invoke 和 warm_invoke 的执行耗时。
    """
    probe_df = dfs.get("cold_start_probe", pd.DataFrame())

    if probe_df.empty or "phase" not in probe_df.columns:
        return pd.DataFrame()

    invoke_df = probe_df[probe_df["phase"].isin(["first_invoke", "warm_invoke"])]

    if invoke_df.empty:
        return pd.DataFrame()

    return (
        invoke_df
        .groupby("phase")
        .agg(
            request_events=("phase_duration", "count"),
            avg_invoke_duration=("phase_duration", "mean"),
            min_invoke_duration=("phase_duration", "min"),
            max_invoke_duration=("phase_duration", "max"),
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

    phase_summary_df = build_phase_summary(dfs)
    phase_summary_path = output_dir / "cold_start_phase_summary.csv"
    phase_summary_df.to_csv(phase_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", phase_summary_path)

    replica_path_df = build_replica_cold_path_summary(dfs)
    replica_path_path = output_dir / "cold_start_replica_path_summary.csv"
    replica_path_df.to_csv(replica_path_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", replica_path_path)

    warm_cold_df = build_warm_cold_compare(dfs)
    warm_cold_path = output_dir / "cold_start_warm_cold_compare.csv"
    warm_cold_df.to_csv(warm_cold_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", warm_cold_path)

    dfs["cold_start_phase_summary"] = phase_summary_df
    dfs["cold_start_replica_path_summary"] = replica_path_df
    dfs["cold_start_warm_cold_compare"] = warm_cold_df

    return dfs
