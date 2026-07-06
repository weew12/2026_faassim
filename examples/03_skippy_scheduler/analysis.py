"""
文件作用：Skippy 调度样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取调度相关 DataFrame，并保存到 outputs/ 目录。

新增的关键导出：
- skippy_feasible_nodes_per_pod.csv：每个 pod 的可行节点数（论文 demo 关键图）
- skippy_node_scheduling_stats.csv：按 node 详细分组的调度统计（含 arch）
- skippy_scheduler_summary.csv：增强版摘要
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "skippy_scheduler_result",
    "skippy_scheduler_candidate",
    "schedule",
    "allocation",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
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


def build_scheduler_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成增强版 Skippy 调度摘要。

    摘要字段（按论文 demo 关心维度排序）：
    - total_pods_scheduled：被调度的 pod 总数
    - schedule_result_events / schedule_metric_events / candidate_snapshot_events
    - selected_node_count：被选中的不同节点数
    - max_feasible_nodes / min_feasible_nodes：每个 pod 的可行节点数范围
    - pods_with_needed_images / pods_with_cached_image：首调 vs 复用
    - avg_feasible_nodes_full
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    candidate_df = dfs.get("skippy_scheduler_candidate", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame([{
            "total_pods_scheduled": 0,
            "schedule_result_events": 0,
            "schedule_metric_events": len(schedule_df),
            "candidate_snapshot_events": len(candidate_df),
            "selected_node_count": 0,
            "max_feasible_nodes": 0,
            "min_feasible_nodes": 0,
            "pods_with_needed_images": 0,
            "pods_with_cached_image": 0,
            "avg_feasible_nodes_full": None,
        }])

    selected_node_count = result_df["selected_node"].nunique() if "selected_node" in result_df.columns else 0
    max_feasible = int(result_df["feasible_nodes_full"].max()) if "feasible_nodes_full" in result_df.columns else 0
    min_feasible = int(result_df["feasible_nodes_full"].min()) if "feasible_nodes_full" in result_df.columns else 0
    avg_feasible = float(result_df["feasible_nodes_full"].mean()) if "feasible_nodes_full" in result_df.columns else None

    # 首调 vs 复用：needed_images_count > 0 表示需要拉新镜像
    if "needed_images_count" in result_df.columns:
        pods_with_needed = int((result_df["needed_images_count"] > 0).sum())
        pods_with_cached = int((result_df["needed_images_count"] == 0).sum())
    else:
        pods_with_needed = None
        pods_with_cached = None

    return pd.DataFrame([{
        "total_pods_scheduled": len(result_df),
        "schedule_result_events": len(result_df),
        "schedule_metric_events": len(schedule_df),
        "candidate_snapshot_events": len(candidate_df),
        "selected_node_count": selected_node_count,
        "max_feasible_nodes": max_feasible,
        "min_feasible_nodes": min_feasible,
        "pods_with_needed_images": pods_with_needed,
        "pods_with_cached_image": pods_with_cached,
        "avg_feasible_nodes_full": avg_feasible,
    }])


def build_selected_node_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计调度结果中目标节点的分布。
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())

    if result_df.empty or "selected_node" not in result_df.columns:
        return pd.DataFrame()

    group_columns = [
        col for col in ["selected_node", "needed_images"]
        if col in result_df.columns
    ]

    return (
        result_df
        .groupby(group_columns)
        .size()
        .reset_index(name="scheduled_pods")
        .sort_values("scheduled_pods", ascending=False)
    )


def build_feasible_nodes_per_pod(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    论文 demo 关键图：每个 pod 的可行节点数。

    返回列：pod_name / all_nodes / feasible_nodes_full / returned_feasible_nodes /
            needed_images_count / selected_node

    用于画图：
    - x=pod_name, y=feasible_nodes_full 柱状图
    - 直观看出 Skippy 资源过滤对每个 pod 的影响
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())

    if result_df.empty or "pod_name" not in result_df.columns:
        return pd.DataFrame()

    preferred = [
        "pod_name",
        "all_nodes",
        "feasible_nodes_full",
        "returned_feasible_nodes",
        "needed_images_count",
        "selected_node",
    ]
    existing = [c for c in preferred if c in result_df.columns]

    return (
        result_df[existing]
        .sort_values("pod_name")
        .reset_index(drop=True)
    )


def build_node_scheduling_stats(sim, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    论文 demo 关键图：按 node 详细分组的调度统计（含 arch）。

    返回列：node_name / arch / node_type / scheduled_pod_count / pods

    用于画图：
    - 按 arch 分组看调度分布（如 arm32/x86/aarch64）
    - 按 node_type 分组看（sbc/server/cloud 等）

    关于 arch/node_type 字段：
    candidate_df 只有前 30 个节点的信息（受 max_candidate_log_rows 限制），
    不一定包含被调度的 server_0 等节点。
    本函数会从 sim.env.cluster 兜底查找节点的 labels。
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())
    candidate_df = dfs.get("skippy_scheduler_candidate", pd.DataFrame())

    if result_df.empty or "selected_node" not in result_df.columns:
        return pd.DataFrame()

    # 1) 从 candidate_df 收集 (arch, node_type) 信息
    node_info = {}
    if not candidate_df.empty and "node_name" in candidate_df.columns:
        for _, row in candidate_df.iterrows():
            nname = row.get("node_name")
            if nname not in node_info:
                node_info[nname] = {
                    "arch": row.get("arch"),
                    "node_type": row.get("node_type"),
                }

    # 2) 兜底：对于不在 candidate_df 里的节点，从 sim.env.cluster 找
    selected_counts = result_df["selected_node"].value_counts().to_dict()
    missing_nodes = [n for n in selected_counts if n not in node_info]
    if missing_nodes and sim is not None:
        try:
            all_nodes = sim.env.cluster.list_nodes()
            node_by_name = {n.name: n for n in all_nodes}
            for nname in missing_nodes:
                node = node_by_name.get(nname)
                if node is None:
                    continue
                arch = node.labels.get("beta.kubernetes.io/arch")
                node_type = node.labels.get("ether.edgerun.io/type")
                node_info[nname] = {"arch": arch, "node_type": node_type}
        except Exception as err:
            logger.warning("failed to lookup node info from cluster: %s", err)

    rows = []
    for node_name, count in selected_counts.items():
        info = node_info.get(node_name, {})
        rows.append({
            "node_name": node_name,
            "arch": info.get("arch"),
            "node_type": info.get("node_type"),
            "scheduled_pod_count": int(count),
        })

    return (
        pd.DataFrame(rows)
        .sort_values("scheduled_pod_count", ascending=False)
        .reset_index(drop=True)
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

    # 新增：每个 pod 的可行节点数（论文 demo 关键图）
    feasible_per_pod_df = build_feasible_nodes_per_pod(dfs)
    feasible_per_pod_path = output_dir / "skippy_feasible_nodes_per_pod.csv"
    feasible_per_pod_df.to_csv(feasible_per_pod_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", feasible_per_pod_path)

    # 新增：按 node 详细分组的调度统计
    node_stats_df = build_node_scheduling_stats(sim, dfs)
    node_stats_path = output_dir / "skippy_node_scheduling_stats.csv"
    node_stats_df.to_csv(node_stats_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", node_stats_path)

    summary_df = build_scheduler_summary(dfs)
    summary_path = output_dir / "skippy_scheduler_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    selected_node_df = build_selected_node_distribution(dfs)
    selected_node_path = output_dir / "skippy_selected_node_distribution.csv"
    selected_node_df.to_csv(selected_node_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", selected_node_path)

    dfs["skippy_feasible_nodes_per_pod"] = feasible_per_pod_df
    dfs["skippy_node_scheduling_stats"] = node_stats_df
    dfs["skippy_scheduler_summary"] = summary_df
    dfs["skippy_selected_node_distribution"] = selected_node_df

    return dfs
