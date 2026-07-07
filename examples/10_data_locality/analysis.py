"""
文件作用：data_locality 样例的指标导出与对比分析工具。

该文件负责导出每个实验场景中的数据下载、网络流、调度结果和调用指标，
并生成跨场景对比摘要。

新增的关键导出：
- candidate_vs_actual_join.csv：把每个场景的 candidate.csv（每个候选节点的
  estimated_download_time）和 data_locality_download.csv（实际下载时长）按
  (scenario, candidate_node) 对齐，证明 Skippy DataLocalityPriority 估算的下载时间
  和实际 simulate_data_download() 跑的下载时间一致。
- download_theoretical_check.csv：按拓扑链路带宽（near_link=200Mbps, mid_link=60Mbps,
  far_link=10Mbps）和数据大小（64M）反算理论下载时间，与 summary 的 total_download_duration
  对比，验证 faas-sim 网络模型和真实带宽的吻合程度。
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

# 拓扑链路带宽（Mbps），来自 topology.py
# - near_link: 200 Mbps
# - mid_link: 60 Mbps
# - far_link: 10 Mbps
LINK_BANDWIDTH_MBPS = {
    "near_link": 200,
    "mid_link": 60,
    "far_link": 10,
}


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

    # 调用 × 调度 candidate join
    candidate_actual_df = build_candidate_vs_actual_join(scenario_name, dfs)
    candidate_actual_path = scenario_dir / "candidate_vs_actual_join.csv"
    candidate_actual_df.to_csv(candidate_actual_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", candidate_actual_path)

    summary_df = build_scenario_summary(scenario_name, dfs)
    summary_path = scenario_dir / "data_locality_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    dfs["candidate_vs_actual_join"] = candidate_actual_df
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

    # 理论下载时间：根据所选节点对应的链路带宽 + 数据大小算
    theoretical_download_duration = None
    if selected_node and total_data_flow_bytes:
        link_for_node = {
            "edge_near": "near_link",
            "edge_mid": "mid_link",
            "edge_far": "far_link",
        }.get(selected_node)
        if link_for_node and link_for_node in LINK_BANDWIDTH_MBPS:
            # bandwidth in Mbps = megabits/s; bytes → bits / bandwidth = seconds
            bandwidth_mbps = LINK_BANDWIDTH_MBPS[link_for_node]
            bandwidth_bytes_per_s = bandwidth_mbps / 8 * 1024 * 1024  # 1 Mbps = 1e6 bits/s, /8 = bytes/s
            theoretical_download_duration = total_data_flow_bytes / bandwidth_bytes_per_s

    return pd.DataFrame([{
        "scenario": scenario_name,
        "selected_node": selected_node,
        "download_events": len(download_df),
        "total_download_duration": total_download_duration,
        "avg_download_duration": avg_download_duration,
        "data_flow_events": len(data_flow_df),
        "total_data_flow_duration": total_data_flow_duration,
        "total_data_flow_bytes": total_data_flow_bytes,
        "theoretical_download_duration": theoretical_download_duration,
        "theoretical_vs_actual_diff": (
            (total_download_duration - theoretical_download_duration)
            if (total_download_duration is not None and theoretical_download_duration is not None)
            else None
        ),
    }])


def build_candidate_vs_actual_join(scenario_name: str, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    把 candidate.csv 和 data_locality_download.csv 按 (candidate_node) 对齐。

    candidate.csv（仅 data_locality_aware 场景有记录）给出每个候选节点的：
    - estimated_download_time   Skippy DataLocalityPriority 估算的下载时间
    - best_bandwidth_bytes_per_s 该节点到存储节点的最大可用带宽

    data_locality_download.csv 给出实际选择的节点和实际下载时长。

    把两者按 candidate_node 对齐后：
    - 如果 candidate_node == selected_node，则 expected = estimated_download_time，
      actual = download_duration，论文 demo 关键证据
    - 其他候选节点只能拿到 expected 值（actual 为 None，因为没真在那节点跑）

    forced_remote 场景没有 candidate 记录，join 输出 selected_node 的实际一行 + 说明。
    """
    candidate_df = dfs.get("data_locality_candidate", pd.DataFrame()).copy()
    download_df = dfs.get("data_locality_download", pd.DataFrame()).copy()
    scheduler_df = dfs.get("data_locality_scheduler_result", pd.DataFrame()).copy()

    if download_df.empty:
        return pd.DataFrame([{
            "scenario": scenario_name,
            "join_rows": 0,
            "message": "no data_locality_download records",
        }])

    # 找到实际 selected_node
    selected_node = None
    if not scheduler_df.empty and "selected_node" in scheduler_df.columns:
        sel = scheduler_df["selected_node"].dropna()
        if not sel.empty:
            selected_node = str(sel.iloc[0])

    rows: List[dict] = []
    if not candidate_df.empty and "candidate_node" in candidate_df.columns:
        # 按 candidate_node 遍历
        for _, cand in candidate_df.iterrows():
            cand_node = str(cand.get("candidate_node"))
            row = {
                "scenario": scenario_name,
                "candidate_node": cand_node,
                "selected_node": selected_node,
                "is_selected": cand_node == selected_node,
                "estimated_download_time": float(cand.get("estimated_download_time"))
                    if pd.notna(cand.get("estimated_download_time")) else None,
                "best_bandwidth_mbps": float(cand.get("best_bandwidth_mbps"))
                    if pd.notna(cand.get("best_bandwidth_mbps")) else None,
                "storage_node": cand.get("storage_node"),
            }
            # 如果是实际选中的节点，从 download_df 拿 actual duration
            if cand_node == selected_node and not download_df.empty:
                actual = download_df[download_df["node_name"] == cand_node]
                if not actual.empty:
                    row["actual_download_duration"] = float(actual["download_duration"].iloc[0])
                    if row["estimated_download_time"] is not None:
                        row["estimated_vs_actual_diff"] = (
                            row["actual_download_duration"] - row["estimated_download_time"]
                        )
                        row["match_tolerance_5pct"] = (
                            abs(row["estimated_vs_actual_diff"]) <
                            0.05 * row["actual_download_duration"]
                        )
            rows.append(row)
    else:
        # forced_remote 场景：只记录 actual 的一行
        for _, dl in download_df.iterrows():
            rows.append({
                "scenario": scenario_name,
                "candidate_node": dl.get("node_name"),
                "selected_node": dl.get("node_name"),
                "is_selected": True,
                "estimated_download_time": None,
                "best_bandwidth_mbps": None,
                "storage_node": dl.get("storage_nodes"),
                "actual_download_duration": float(dl["download_duration"])
                    if pd.notna(dl.get("download_duration")) else None,
                "estimated_vs_actual_diff": None,
                "match_tolerance_5pct": None,
                "note": "forced_remote scenario: candidate records not logged",
            })

    return pd.DataFrame(rows)


def export_comparison(output_dir: Path, scenario_summaries: List[pd.DataFrame]) -> pd.DataFrame:
    """
    导出跨场景对比摘要。

    同时加一行 paper_demo_highlight：
    - aware_download / forced_download
    - speedup_ratio = forced / aware
    - theoretical_aware / theoretical_forced
    """
    if scenario_summaries:
        comparison_df = pd.concat(scenario_summaries, ignore_index=True)
    else:
        comparison_df = pd.DataFrame()

    comparison_path = output_dir / "data_locality_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", comparison_path)

    # 加 paper demo 关键摘要
    if len(comparison_df) == 2:
        aware = comparison_df[comparison_df.scenario == "data_locality_aware"]
        forced = comparison_df[comparison_df.scenario == "forced_remote"]
        if not aware.empty and not forced.empty:
            aware_dur = float(aware["total_download_duration"].iloc[0])
            forced_dur = float(forced["total_download_duration"].iloc[0])
            aware_th = aware["theoretical_download_duration"].iloc[0]
            forced_th = forced["theoretical_download_duration"].iloc[0]
            speedup = forced_dur / aware_dur if aware_dur > 0 else None

            highlight = pd.DataFrame([{
                "metric": "aware_download_seconds",
                "value": aware_dur,
            }, {
                "metric": "forced_download_seconds",
                "value": forced_dur,
            }, {
                "metric": "speedup_ratio_forced_over_aware",
                "value": speedup,
            }, {
                "metric": "aware_theoretical_seconds",
                "value": aware_th,
            }, {
                "metric": "forced_theoretical_seconds",
                "value": forced_th,
            }, {
                "metric": "aware_actual_vs_theoretical_diff",
                "value": (aware_dur - float(aware_th)) if pd.notna(aware_th) else None,
            }, {
                "metric": "forced_actual_vs_theoretical_diff",
                "value": (forced_dur - float(forced_th)) if pd.notna(forced_th) else None,
            }])
            highlight_path = output_dir / "data_locality_paper_highlight.csv"
            highlight.to_csv(highlight_path, index=False, encoding="utf-8-sig")
            logger.info("saved %s", highlight_path)

    return comparison_df