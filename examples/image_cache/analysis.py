"""
文件作用：image_cache 样例的指标导出与对比分析工具。

该文件负责导出每个场景中的镜像缓存探针、网络流、调度和部署指标，
并生成 same_node_cache_reuse 与 different_node_cold_pull 的对比摘要。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "image_cache_probe",
    "flow",
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
    导出单个镜像缓存场景的结果。
    """
    scenario_dir = output_dir / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = scenario_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    summary_df = build_scenario_summary(scenario_name, dfs)
    summary_path = scenario_dir / "image_cache_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    node_summary_df = build_node_image_cache_summary(dfs)
    node_summary_path = scenario_dir / "image_cache_node_summary.csv"
    node_summary_df.to_csv(node_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", node_summary_path)

    dfs["image_cache_summary"] = summary_df
    dfs["image_cache_node_summary"] = node_summary_df

    return dfs


def build_scenario_summary(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成单个场景摘要。
    """
    probe_df = dfs.get("image_cache_probe", pd.DataFrame())
    flow_df = dfs.get("flow", pd.DataFrame())

    if probe_df.empty:
        return pd.DataFrame([{
            "scenario": scenario_name,
            "deploy_events": 0,
        }])

    docker_flow_df = flow_df
    if not flow_df.empty and "action_type" in flow_df.columns:
        docker_flow_df = flow_df[flow_df["action_type"] == "docker_pull"]

    cache_hit_before_count = (
        int(probe_df["cache_hit_before"].astype(bool).sum())
        if "cache_hit_before" in probe_df.columns
        else None
    )

    cold_pull_count = (
        int((~probe_df["cache_hit_before"].astype(bool)).sum())
        if "cache_hit_before" in probe_df.columns
        else None
    )

    total_pull_duration = (
        float(probe_df["pull_duration"].sum())
        if "pull_duration" in probe_df.columns
        else None
    )

    return pd.DataFrame([{
        "scenario": scenario_name,
        "deploy_events": len(probe_df),
        "cache_hit_before_count": cache_hit_before_count,
        "cold_pull_count": cold_pull_count,
        "total_pull_duration": total_pull_duration,
        "avg_pull_duration": float(probe_df["pull_duration"].mean()) if "pull_duration" in probe_df.columns else None,
        "docker_pull_flow_events": len(docker_flow_df),
        "docker_pull_total_bytes": int(docker_flow_df["bytes"].sum()) if not docker_flow_df.empty and "bytes" in docker_flow_df.columns else None,
    }])


def build_node_image_cache_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按节点统计镜像缓存观测结果。
    """
    probe_df = dfs.get("image_cache_probe", pd.DataFrame())

    if probe_df.empty or "node_name" not in probe_df.columns:
        return pd.DataFrame()

    return (
        probe_df
        .groupby(["scenario", "node_name", "image"])
        .agg(
            deploy_events=("pull_duration", "count"),
            cache_hits_before=("cache_hit_before", "sum"),
            avg_pull_duration=("pull_duration", "mean"),
            max_cached_image_count=("cached_image_count_after", "max"),
        )
        .reset_index()
    )


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比摘要。
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "image_cache_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    return comparison_df
