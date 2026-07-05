"""
文件作用：data_locality 样例的指标导出与对比分析工具。

该文件负责导出每个实验场景中的数据下载、网络流、调度结果和调用指标，
并生成跨场景对比摘要。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "data_locality_scheduler_result",
    "data_locality_candidate",
    "data_locality_download",
    "flow",
    "network",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
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


def export_scenario_outputs(sim, scenario_name: str, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出单个场景的仿真指标。
    """
    scenario_dir = output_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = scenario_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    summary_df = build_scenario_summary(scenario_name, dfs)
    summary_path = scenario_dir / "data_locality_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    dfs["data_locality_summary"] = summary_df
    return dfs


def build_scenario_summary(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成单个场景摘要。
    """
    download_df = dfs.get("data_locality_download", pd.DataFrame())
    flow_df = dfs.get("flow", pd.DataFrame())
    scheduler_df = dfs.get("data_locality_scheduler_result", pd.DataFrame())

    selected_node = None
    if not scheduler_df.empty and "selected_node" in scheduler_df.columns:
        selected_node = ";".join(sorted(scheduler_df["selected_node"].dropna().astype(str).unique()))

    total_download_duration = None
    avg_download_duration = None
    if not download_df.empty and "download_duration" in download_df.columns:
        total_download_duration = float(download_df["download_duration"].sum())
        avg_download_duration = float(download_df["download_duration"].mean())

    data_flow_df = flow_df
    if not flow_df.empty and "action_type" in flow_df.columns:
        data_flow_df = flow_df[flow_df["action_type"] == "data_download"]

    total_data_flow_duration = None
    total_data_flow_bytes = None
    if not data_flow_df.empty:
        if "duration" in data_flow_df.columns:
            total_data_flow_duration = float(data_flow_df["duration"].sum())
        if "bytes" in data_flow_df.columns:
            total_data_flow_bytes = int(data_flow_df["bytes"].sum())

    return pd.DataFrame([{
        "scenario": scenario_name,
        "selected_node": selected_node,
        "download_events": len(download_df),
        "total_download_duration": total_download_duration,
        "avg_download_duration": avg_download_duration,
        "data_flow_events": len(data_flow_df),
        "total_data_flow_duration": total_data_flow_duration,
        "total_data_flow_bytes": total_data_flow_bytes,
    }])


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比摘要。
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "data_locality_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    return comparison_df
