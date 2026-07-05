"""
文件作用：cache_aware_scheduler 样例的指标导出与对比分析工具。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cache_aware_candidate",
    "cache_aware_scheduler_result",
    "cache_aware_request_probe",
    "cache_aware_workload_request",
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


def export_scenario_outputs(sim, scenario_name: str, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出单个场景结果。
    """
    scenario_dir = output_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = scenario_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    summary_df = build_scenario_summary(scenario_name, dfs)
    summary_path = scenario_dir / "cache_aware_scheduler_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    function_summary_df = build_function_summary(dfs)
    function_summary_path = scenario_dir / "cache_aware_function_summary.csv"
    function_summary_df.to_csv(function_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", function_summary_path)

    dfs["cache_aware_scheduler_summary"] = summary_df
    dfs["cache_aware_function_summary"] = function_summary_df

    return dfs


def build_scenario_summary(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成单个场景摘要。
    """
    probe_df = dfs.get("cache_aware_request_probe", pd.DataFrame())
    result_df = dfs.get("cache_aware_scheduler_result", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "scenario": scenario_name,
            "request_events": 0,
        }])

    cache_hit_count = int(probe_df["cache_hit"].astype(bool).sum()) if "cache_hit" in probe_df.columns else None

    selected_nodes = None
    if not result_df.empty and "selected_node" in result_df.columns:
        selected_nodes = ";".join(sorted(result_df["selected_node"].dropna().astype(str).unique()))

    return pd.DataFrame([{
        "scenario": scenario_name,
        "request_events": len(probe_df),
        "cache_hit_count": cache_hit_count,
        "cache_hit_rate": cache_hit_count / len(probe_df) if cache_hit_count is not None else None,
        "avg_final_duration": float(probe_df["final_duration"].mean()) if "final_duration" in probe_df.columns else None,
        "total_cold_start_penalty": float(probe_df["cold_start_penalty"].sum()) if "cold_start_penalty" in probe_df.columns else None,
        "schedule_events": len(result_df),
        "selected_nodes": selected_nodes,
    }])


def build_function_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按函数生成请求结果摘要。
    """
    probe_df = dfs.get("cache_aware_request_probe", pd.DataFrame())

    if probe_df.empty or "function_name" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby("function_name")
        .agg(
            request_count=("request_id", "count"),
            cache_hits=("cache_hit", "sum"),
            avg_final_duration=("final_duration", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
        .assign(cache_hit_rate=lambda df: df["cache_hits"] / df["request_count"])
    )


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比结果。
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "cache_aware_scheduler_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    return comparison_df
