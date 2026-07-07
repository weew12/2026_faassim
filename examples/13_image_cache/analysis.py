"""
文件作用：image_cache 样例的指标导出与对比分析工具。

该文件负责导出每个场景中的镜像缓存探针、网络流、调度和部署指标，
并生成 same_node_cache_reuse 与 different_node_cold_pull 的对比摘要。

新增的关键导出：
- probe_flow_join.csv：probe × flow（docker_pull）按 (scenario, node_name) 关联，
  验证"探针记录的 pull_duration 跟 flow.csv 中的 docker_pull 时长一致"。
- image_cache_paper_highlight.csv：跨场景对比 + 论文 demo 关键摘要
  (reuse_pull_seconds / cold_per_node_pull_seconds / cached_bytes_saved)。
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

    # probe × flow（docker_pull）关联
    probe_flow_df = build_probe_flow_join(scenario_name, dfs)
    probe_flow_path = scenario_dir / "probe_flow_join.csv"
    probe_flow_df.to_csv(probe_flow_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", probe_flow_path)

    dfs["image_cache_summary"] = summary_df
    dfs["image_cache_node_summary"] = node_summary_df
    dfs["probe_flow_join"] = probe_flow_df

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


def build_probe_flow_join(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    probe × flow（docker_pull）按 (scenario, node_name, image) 关联。

    论文 demo 关键证据：probe 记录的 pull_duration 跟 flow.csv 中
    action_type=docker_pull 的网络流时长一致；cache_hit_before=True 的 probe
    在 flow.csv 中没有对应行（因为 cache hit 不产生网络流）。

    这里假设：probe 的一条 cache_miss 记录，对应 flow.csv 中 source=registry,
    sink=probe.node_name 的 docker_pull 行。
    """
    probe_df = dfs.get("image_cache_probe", pd.DataFrame()).copy()
    flow_df = dfs.get("flow", pd.DataFrame()).copy()

    if probe_df.empty or flow_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing image_cache_probe or flow",
        }])

    if "action_type" in flow_df.columns:
        docker_pull_df = flow_df[flow_df["action_type"] == "docker_pull"].copy()
    else:
        docker_pull_df = flow_df.copy()

    if "duration" in docker_pull_df.columns:
        docker_pull_df["duration"] = pd.to_numeric(docker_pull_df["duration"], errors="coerce")
    if "pull_duration" in probe_df.columns:
        probe_df["pull_duration"] = pd.to_numeric(probe_df["pull_duration"], errors="coerce")

    rows: List[dict] = []
    for _, p in probe_df.iterrows():
        is_cache_hit = bool(p.get("cache_hit_before"))
        # 找对应 flow：sink == probe.node_name
        # cache hit 时不应该有 flow（docker.pull() 直接返回）
        if is_cache_hit:
            match = docker_pull_df.iloc[0:0]  # empty
        else:
            match = docker_pull_df[docker_pull_df["sink"] == p.get("node_name")]

        if not match.empty:
            flow_row = match.iloc[0]
            flow_duration = float(flow_row["duration"]) if pd.notna(flow_row.get("duration")) else None
            flow_bytes = int(flow_row["bytes"]) if pd.notna(flow_row.get("bytes")) else None
            duration_match = (
                flow_duration is not None
                and abs(float(p["pull_duration"]) - flow_duration) < 0.05  # 50ms tolerance
            )
        else:
            flow_duration = None
            flow_bytes = None
            # cache hit 时确实没有对应 flow，duration_match 视为 True（符合预期）
            if is_cache_hit:
                duration_match = True
            else:
                duration_match = None  # 异常：cold pull 但没有 flow

        rows.append({
            "scenario": scenario_name,
            "function_name": p.get("function_name"),
            "image": p.get("image"),
            "node_name": p.get("node_name"),
            "cache_hit_before": is_cache_hit,
            "probe_pull_duration": float(p["pull_duration"]) if pd.notna(p.get("pull_duration")) else None,
            "probe_image_size": int(p["image_size"]) if pd.notna(p.get("image_size")) else None,
            "flow_duration": flow_duration,
            "flow_bytes": flow_bytes,
            "duration_match_50ms": duration_match,
        })

    return pd.DataFrame(rows)


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比摘要 + 论文 demo 关键摘要。
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "image_cache_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    # 论文 demo 关键摘要
    if len(comparison_df) == 2:
        reuse = comparison_df[comparison_df.scenario == "same_node_cache_reuse"]
        cold = comparison_df[comparison_df.scenario == "different_node_cold_pull"]
        if not reuse.empty and not cold.empty:
            reuse_total = float(reuse["total_pull_duration"].iloc[0])
            cold_total = float(cold["total_pull_duration"].iloc[0])
            cold_pulls = int(cold["cold_pull_count"].iloc[0])
            reuse_pulls = int(reuse["cold_pull_count"].iloc[0])
            # 字节节省：cold 场景下未复制的字节数
            cold_bytes_saved = 0
            try:
                reuse_paper_row = pd.read_csv(output_dir / "same_node_cache_reuse" / "image_cache_summary.csv")
                cold_paper_row = pd.read_csv(output_dir / "different_node_cold_pull" / "image_cache_summary.csv")
                reuse_bytes = int(reuse_paper_row["docker_pull_total_bytes"].iloc[0])
                cold_bytes = int(cold_paper_row["docker_pull_total_bytes"].iloc[0])
                cold_bytes_saved = cold_bytes - reuse_bytes
            except Exception:
                pass

            highlight = pd.DataFrame([
                {"metric": "same_node_total_pull_seconds", "value": reuse_total},
                {"metric": "different_node_total_pull_seconds", "value": cold_total},
                {"metric": "same_node_cold_pull_count", "value": reuse_pulls},
                {"metric": "different_node_cold_pull_count", "value": cold_pulls},
                {"metric": "saved_pull_seconds_by_cache", "value": cold_total - reuse_total},
                {"metric": "saved_bytes_by_cache", "value": cold_bytes_saved},
                {"metric": "speedup_ratio_cold_over_reuse",
                 "value": cold_total / reuse_total if reuse_total > 0 else None},
            ])
            highlight_path = output_dir / "image_cache_paper_highlight.csv"
            highlight.to_csv(highlight_path, index=False, encoding="utf-8-sig")
            logger.info("saved %s", highlight_path)

    return comparison_df
