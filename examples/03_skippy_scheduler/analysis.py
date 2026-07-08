"""
文件作用：Skippy 调度样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取调度相关 DataFrame，并保存到 outputs/ 目录。

关键导出（沿用 02_load_balancer 的 paper_highlight / data_self_check 模式）：
- skippy_schedule_probe_invocation_join.csv：
    汇总 schedule_probe / invoke_dispatch_probe / invocations 的一致性
- skippy_invoke_probe_invocation_join.csv：
    逐条关联 invoke_dispatch_probe 和 invocations，验证 dispatch 与实际 invoke 一致
- skippy_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value
- skippy_self_check.csv：
    数据自检（PASS/FAIL）
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "skippy_scheduler_result",
    "skippy_scheduler_candidate",
    "schedule_probe",
    "schedule",
    "allocation",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
    "flow",
    "invoke_dispatch_probe",
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
    - pods_with_filtered_nodes / filtered_candidate_nodes：资源过滤效果
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
    all_nodes = int(result_df["all_nodes"].max()) if "all_nodes" in result_df.columns else 0
    max_feasible = int(result_df["feasible_nodes_full"].max()) if "feasible_nodes_full" in result_df.columns else 0
    min_feasible = int(result_df["feasible_nodes_full"].min()) if "feasible_nodes_full" in result_df.columns else 0
    avg_feasible = float(result_df["feasible_nodes_full"].mean()) if "feasible_nodes_full" in result_df.columns else None
    pods_with_filtered_nodes = 0
    filtered_candidate_nodes = 0
    if {"all_nodes", "feasible_nodes_full"}.issubset(result_df.columns):
        filtered = result_df["all_nodes"].astype(int) - result_df["feasible_nodes_full"].astype(int)
        pods_with_filtered_nodes = int((filtered > 0).sum())
        filtered_candidate_nodes = int(filtered.sum())

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
        "all_nodes": all_nodes,
        "max_feasible_nodes": max_feasible,
        "min_feasible_nodes": min_feasible,
        "pods_with_filtered_nodes": pods_with_filtered_nodes,
        "filtered_candidate_nodes": filtered_candidate_nodes,
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

    关于 arch/node_type 字段：
    candidate_df 只记录前 max_candidate_log_rows 个节点（默认 30）的 arch/type，
    不一定包含被调度的节点。本函数会从 sim.env.cluster 兜底查找节点的 labels。
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
    selected_pods_by_node = (
        result_df.groupby("selected_node")["pod_name"]
        .apply(lambda s: ";".join(sorted(s.astype(str).tolist())))
        .to_dict()
    )
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
            "pods": selected_pods_by_node.get(node_name, ""),
        })

    return (
        pd.DataFrame(rows)
        .sort_values("scheduled_pod_count", ascending=False)
        .reset_index(drop=True)
    )


def build_invoke_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    逐条关联 invoke_dispatch_probe 与 invocations。

    关联键使用 (function_name, replica_id, simtime/t_start)。这比只看总数更严格，
    能验证 simulator 派发探针和 faas-sim invocation 指标在函数、节点、时间上对应。
    """
    probe_df = dfs.get("invoke_dispatch_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame()

    required_probe = {"function_name", "replica_id", "simtime", "node"}
    required_inv = {"function_name", "replica_id", "t_start", "node", "t_exec"}
    if not required_probe.issubset(probe_df.columns) or not required_inv.issubset(inv_df.columns):
        return pd.DataFrame()

    rows = []
    for (fn, replica_id), probe_grp in probe_df.groupby(["function_name", "replica_id"], dropna=False):
        probe_sorted = probe_grp.sort_values("simtime").reset_index(drop=True)
        inv_grp = inv_df[
            (inv_df["function_name"] == fn)
            & (inv_df["replica_id"].astype(str) == str(replica_id))
        ].sort_values("t_start").reset_index(drop=True)

        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            probe = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            simtime_match = abs(float(probe["simtime"]) - float(inv["t_start"])) < 1e-6
            node_match = str(probe["node"]) == str(inv["node"])
            rows.append({
                "function_name": fn,
                "replica_id": replica_id,
                "probe_simtime": float(probe["simtime"]),
                "inv_t_start": float(inv["t_start"]),
                "inv_t_exec": float(inv["t_exec"]),
                "probe_node": probe["node"],
                "inv_node": inv["node"],
                "simtime_match": bool(simtime_match),
                "node_match": bool(node_match),
            })

    return pd.DataFrame(rows)


def build_schedule_probe_invocation_join(
    dfs: Dict[str, pd.DataFrame],
    invoke_join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    关联 schedule_probe（after-phase）和 invocations 事件，验证调度时序与实际
    invoke 时序一致（仿 02 的 probe×invocation join 模式）。

    这是样例级汇总：调度后 probe、调度结果、invoke dispatch probe 和 invocations
    四类事件数量应相互对应。
    """
    probe_df = dfs.get("schedule_probe", pd.DataFrame())
    inv_df = dfs.get("invocations", pd.DataFrame())
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())
    dispatch_df = dfs.get("invoke_dispatch_probe", pd.DataFrame())

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "total_schedule_probe_after": 0,
            "total_schedule_results": len(result_df),
            "total_dispatch_probes": len(dispatch_df),
            "total_invocation_events": 0,
            "pods_with_probe": 0,
            "functions_with_invocations": 0,
            "invoke_probe_join_rows": len(invoke_join_df),
            "invoke_probe_join_all_match": False,
            "probe_invocation_consistent": False,
        }])

    after_probe_df = (
        probe_df[probe_df["phase"] == "after"].copy()
        if "phase" in probe_df.columns
        else probe_df.copy()
    )

    pods_with_probe = int(after_probe_df["pod_name"].nunique()) if "pod_name" in after_probe_df.columns else 0
    functions_with_invocations = int(inv_df["function_name"].nunique()) if "function_name" in inv_df.columns else 0
    total_pods = len(result_df)
    dispatch_total = len(dispatch_df)
    invocation_total = len(inv_df)
    invoke_join_all_match = False
    if not invoke_join_df.empty and {"simtime_match", "node_match"}.issubset(invoke_join_df.columns):
        invoke_join_all_match = bool(
            len(invoke_join_df) == invocation_total
            and invoke_join_df["simtime_match"].all()
            and invoke_join_df["node_match"].all()
        )

    consistent = (
        total_pods > 0
        and pods_with_probe == total_pods
        and len(after_probe_df) == total_pods
        and dispatch_total == invocation_total
        and invoke_join_all_match
        and functions_with_invocations > 0
    )

    return pd.DataFrame([{
        "total_schedule_probe_after": len(after_probe_df),
        "total_schedule_results": total_pods,
        "total_dispatch_probes": dispatch_total,
        "total_invocation_events": invocation_total,
        "pods_with_probe": pods_with_probe,
        "functions_with_invocations": functions_with_invocations,
        "invoke_probe_join_rows": len(invoke_join_df),
        "invoke_probe_join_all_match": bool(invoke_join_all_match),
        "probe_invocation_consistent": bool(consistent),
    }])


def build_paper_highlight(
    result_df: pd.DataFrame,
    feasible_df: pd.DataFrame,
    node_stats_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02_load_balancer 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    total_pods = len(result_df)
    invocation_events = len(inv_df)
    selected_node_count = int(result_df["selected_node"].nunique()) if not result_df.empty and "selected_node" in result_df.columns else 0

    if not result_df.empty and "feasible_nodes_full" in result_df.columns:
        max_feasible = int(result_df["feasible_nodes_full"].max())
        min_feasible = int(result_df["feasible_nodes_full"].min())
        avg_feasible = float(result_df["feasible_nodes_full"].mean())
    else:
        max_feasible = min_feasible = avg_feasible = 0

    all_nodes = int(result_df["all_nodes"].max()) if not result_df.empty and "all_nodes" in result_df.columns else 0
    if not result_df.empty and {"all_nodes", "feasible_nodes_full"}.issubset(result_df.columns):
        filtered = result_df["all_nodes"].astype(int) - result_df["feasible_nodes_full"].astype(int)
        pods_with_filtered = int((filtered > 0).sum())
        filtered_candidates = int(filtered.sum())
    else:
        pods_with_filtered = 0
        filtered_candidates = 0

    if not result_df.empty and "needed_images_count" in result_df.columns:
        pods_with_needed = int((result_df["needed_images_count"] > 0).sum())
        pods_with_cached = int((result_df["needed_images_count"] == 0).sum())
    else:
        pods_with_needed = pods_with_cached = 0

    # 调度分布熵：节点被分配的 pod 数量分布
    if not result_df.empty and "selected_node" in result_df.columns and total_pods > 0:
        per_node = result_df["selected_node"].value_counts()
        # 归一化分布
        probs = per_node.values / per_node.sum()
        # 香农熵
        import math
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    else:
        entropy = 0.0

    # probe×invocation 一致性
    join_consistent = bool(join_df["probe_invocation_consistent"].iloc[0]) if not join_df.empty and "probe_invocation_consistent" in join_df.columns else False

    return pd.DataFrame([
        {"metric": "total_pods_scheduled", "value": total_pods,
         "note": "被 Skippy 调度的 pod 总数"},
        {"metric": "invocation_events", "value": invocation_events,
         "note": "实际函数调用事件总数"},
        {"metric": "selected_node_count", "value": selected_node_count,
         "note": "被选中的不同 node 数量"},
        {"metric": "all_nodes", "value": all_nodes,
         "note": "调度器看到的候选 node 总数"},
        {"metric": "max_feasible_nodes", "value": max_feasible,
         "note": "pod 的最大可行节点数"},
        {"metric": "min_feasible_nodes", "value": min_feasible,
         "note": "pod 的最小可行节点数"},
        {"metric": "avg_feasible_nodes_full", "value": round(avg_feasible, 4),
         "note": "pod 平均可行节点数"},
        {"metric": "pods_with_filtered_nodes", "value": pods_with_filtered,
         "note": "至少过滤掉 1 个候选节点的 pod 数"},
        {"metric": "filtered_candidate_nodes", "value": filtered_candidates,
         "note": "被资源谓词过滤掉的候选节点总次数"},
        {"metric": "pods_with_needed_images", "value": pods_with_needed,
         "note": "目标节点尚无镜像、需要拉取的 pod 数"},
        {"metric": "pods_with_cached_image", "value": pods_with_cached,
         "note": "目标节点已有镜像、可复用缓存的 pod 数"},
        {"metric": "schedule_entropy", "value": round(entropy, 4),
         "note": "调度分布香农熵（越大越分散）"},
        {"metric": "probe_invocation_consistent", "value": bool(join_consistent),
         "note": "schedule_probe × invocations 时序一致性"},
    ])


def data_self_check(
    result_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    feasible_df: pd.DataFrame,
    node_stats_df: pd.DataFrame,
    join_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    Skippy 调度样例的数据自洽检查（沿用 02_load_balancer 的 self_check 模式）。

    不变量：
    1. total_pods_scheduled == 5（small/medium 各 2，large 1）
    2. invocation_events == 40（20 + 12 + 8）
    3. selected_node_count >= 1（至少有 1 个节点被选中）
    4. feasible_nodes_full 一致（所有 pod 都至少有 1 个可行节点）
    5. selected_node 都已记录（不是 None）
    6. 至少 1 个 pod 发生资源过滤
    7. 首调镜像拉取和缓存复用均出现
    8. feasible_per_pod 行数与调度结果一致
    9. node_scheduling_stats 非空
    10. probe×invocation 一致

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    total_pods = len(result_df)
    invocation_events = len(inv_df)
    selected_node_count = int(result_df["selected_node"].nunique()) if not result_df.empty and "selected_node" in result_df.columns else 0

    all_feasible_set = True
    all_selected_set = True
    if not result_df.empty and "feasible_nodes_full" in result_df.columns:
        all_feasible_set = bool((result_df["feasible_nodes_full"] >= 1).all())
    if not result_df.empty and "selected_node" in result_df.columns:
        all_selected_set = bool(result_df["selected_node"].notna().all())

    pods_with_needed = int((result_df["needed_images_count"] > 0).sum()) if not result_df.empty and "needed_images_count" in result_df.columns else 0
    pods_with_cached = int((result_df["needed_images_count"] == 0).sum()) if not result_df.empty and "needed_images_count" in result_df.columns else 0
    pods_with_filtered = 0
    min_feasible_lt_all_nodes = False
    if not result_df.empty and {"all_nodes", "feasible_nodes_full"}.issubset(result_df.columns):
        filtered = result_df["all_nodes"].astype(int) - result_df["feasible_nodes_full"].astype(int)
        pods_with_filtered = int((filtered > 0).sum())
        min_feasible_lt_all_nodes = bool((result_df["feasible_nodes_full"] < result_df["all_nodes"]).any())

    join_consistent = bool(join_df["probe_invocation_consistent"].iloc[0]) if not join_df.empty and "probe_invocation_consistent" in join_df.columns else False

    checks = {
        "01_total_pods_is_5": total_pods == 5,
        "02_invocation_events_is_40": invocation_events == 40,
        "03_selected_node_at_least_1": selected_node_count >= 1,
        "04_all_pods_have_feasible_nodes": all_feasible_set,
        "05_all_selected_node_recorded": all_selected_set,
        "06_resource_filtering_observed": pods_with_filtered >= 1 and min_feasible_lt_all_nodes,
        "07_needed_and_cached_images_observed": pods_with_needed >= 1 and pods_with_cached >= 1,
        "08_feasible_per_pod_rows_match": len(feasible_df) == total_pods,
        "09_node_scheduling_stats_nonempty": len(node_stats_df) >= 1,
        "10_probe_invocation_consistent": join_consistent,
    }

    return checks


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - faas-sim 内置 metric 与示例 probe metric 的 CSV
    - skippy_feasible_nodes_per_pod.csv：每个 pod 的可行节点数（论文 demo 关键图）
    - skippy_node_scheduling_stats.csv：按 node 详细分组的调度统计（含 arch）
    - skippy_scheduler_summary.csv：增强版摘要
    - skippy_selected_node_distribution.csv：selected_node × needed_images 分组
    - skippy_schedule_probe_invocation_join.csv：probe×invocation 时序关联
    - skippy_paper_highlight.csv：论文 demo 关键摘要
    - skippy_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # 每个 pod 的可行节点数（论文 demo 关键图）
    feasible_per_pod_df = build_feasible_nodes_per_pod(dfs)
    feasible_per_pod_path = output_dir / "skippy_feasible_nodes_per_pod.csv"
    feasible_per_pod_df.to_csv(feasible_per_pod_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", feasible_per_pod_path)

    # 按 node 详细分组的调度统计
    node_stats_df = build_node_scheduling_stats(sim, dfs)
    node_stats_path = output_dir / "skippy_node_scheduling_stats.csv"
    node_stats_df.to_csv(node_stats_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", node_stats_path)

    # 增强版摘要
    summary_df = build_scheduler_summary(dfs)
    summary_path = output_dir / "skippy_scheduler_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    # selected_node × needed_images 分组
    selected_node_df = build_selected_node_distribution(dfs)
    selected_node_path = output_dir / "skippy_selected_node_distribution.csv"
    selected_node_df.to_csv(selected_node_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", selected_node_path)

    # probe×invocation join
    invoke_join_df = build_invoke_probe_invocation_join(dfs)
    invoke_join_path = output_dir / "skippy_invoke_probe_invocation_join.csv"
    invoke_join_df.to_csv(invoke_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invoke_join_path)

    join_df = build_schedule_probe_invocation_join(dfs, invoke_join_df)
    join_path = output_dir / "skippy_schedule_probe_invocation_join.csv"
    join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        result_df=dfs.get("skippy_scheduler_result", pd.DataFrame()),
        feasible_df=feasible_per_pod_df,
        node_stats_df=node_stats_df,
        inv_df=dfs.get("invocations", pd.DataFrame()),
        join_df=join_df,
    )
    paper_path = output_dir / "skippy_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        result_df=dfs.get("skippy_scheduler_result", pd.DataFrame()),
        inv_df=dfs.get("invocations", pd.DataFrame()),
        feasible_df=feasible_per_pod_df,
        node_stats_df=node_stats_df,
        join_df=join_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "skippy_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    dfs["skippy_feasible_nodes_per_pod"] = feasible_per_pod_df
    dfs["skippy_node_scheduling_stats"] = node_stats_df
    dfs["skippy_scheduler_summary"] = summary_df
    dfs["skippy_selected_node_distribution"] = selected_node_df
    dfs["skippy_invoke_probe_invocation_join"] = invoke_join_df
    dfs["skippy_schedule_probe_invocation_join"] = join_df
    dfs["skippy_paper_highlight"] = paper_df
    dfs["skippy_self_check"] = check_df

    return dfs
