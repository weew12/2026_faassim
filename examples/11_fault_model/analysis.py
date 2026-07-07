"""
文件作用：fault_model 样例的指标导出与简要分析工具。

该文件负责导出故障探针、故障时间线、调用、调度、资源和部署指标，
并生成请求成败摘要与故障类型分布。

新增的关键导出：
- probe_with_simtime.csv：给 probe.csv 重建 simtime 列
  （probe 原始只有 wall-clock datetime，simtime 需要按 (replica_id, time) 排序后用 (rank+1) 重建，
  因为同一个 replica 上的请求是顺序执行的）。这是把 probe 和 fault_events / invocations
  按 simtime 对齐的前提。
- probe_fault_window_check.csv：probe × fault_events 按 simtime ∈ [start, end] 关联，
  论文 demo 关键证据：每个标记为 node_outage / network_degradation 的请求确实落在
  故障窗口内，证明 fault_model.decide 的窗口判定是精确的。
- probe_invocation_join.csv：probe × invocations 按 (function_name, replica_id, request_id)
  关联，验证 simulator 派发的 final_duration 和 faas-sim 记录的 t_exec 完全一致。
"""

import logging
from pathlib import Path
from typing import Dict, List

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


def _rebuild_probe_simtime(probe_df: pd.DataFrame, function_duration_lookup: Dict[str, float]) -> pd.DataFrame:
    """
    给 probe DataFrame 重建 simtime 列。

    方法：
    - probe 按 (replica_id, wall_clock_time) 排序
    - 同一 replica 的请求是顺序执行的（faas-sim 默认单 replica 串行）
    - 第 1 个请求的 simtime = 0（函数 replica setup 完成后开始）；第 N 个 simtime = sum(前 N-1 个 final_duration)
    - function_duration_lookup 来自 invocations.csv 的 t_exec，提供准确的累计 simtime
    - 因为 invocations 有 (function_name, replica_id, t_start, t_exec) 4 元组，可以按 probe 的 (function_name, replica_id, request_id) 顺序匹配
    """
    if probe_df.empty or "replica_id" not in probe_df.columns:
        return probe_df

    out_rows = []
    # 按 function_name + replica_id 分组
    for (fn, rep_id), sub in probe_df.groupby(["function_name", "replica_id"], dropna=False):
        sub_sorted = sub.sort_index().reset_index(drop=True)
        # 用 invocations 的 (fn, replica_id, request_id, t_start) 反查每条 probe 的 t_start
        # 但 probe 没 request_id 序列号；只能用顺序对齐
        # 取该 (fn, rep_id) 的 invocations，按 t_start 排序，对应位置给 probe
        if (fn, rep_id) in function_duration_lookup:
            inv_times = function_duration_lookup[(fn, rep_id)]
            for i, (_, p) in enumerate(sub_sorted.iterrows()):
                if i < len(inv_times):
                    out_rows.append({
                        **p.to_dict(),
                        "simtime": inv_times[i][0],  # t_start
                        "expected_simtime": inv_times[i][1],  # t_start + t_exec
                    })
                else:
                    out_rows.append({**p.to_dict(), "simtime": None, "expected_simtime": None})
        else:
            for _, p in sub_sorted.iterrows():
                out_rows.append({**p.to_dict(), "simtime": None, "expected_simtime": None})

    return pd.DataFrame(out_rows)


def _build_invocation_simtime_lookup(inv_df: pd.DataFrame) -> Dict[tuple, List[tuple]]:
    """
    从 invocations.csv 构造 (function_name, replica_id) → [(t_start, t_start+t_exec), ...] 映射。

    invocations 按 (function_name, replica_id, t_start) 排序后，每条记录对应一个请求的开始和结束 simtime。
    """
    if inv_df.empty or "t_start" not in inv_df.columns or "t_exec" not in inv_df.columns:
        return {}

    inv_df = inv_df.copy()
    inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")
    inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")

    lookup: Dict[tuple, List[tuple]] = {}
    for (fn, rep), sub in inv_df.groupby(["function_name", "replica_id"], dropna=False):
        sub_sorted = sub.sort_values("t_start")
        lookup[(fn, rep)] = [
            (float(row.t_start), float(row.t_start + row.t_exec))
            for row in sub_sorted.itertuples(index=False)
        ]
    return lookup


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


def build_probe_with_simtime(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    给 probe 重建 simtime 列，便于和 fault_events / invocations 按 simtime 对齐。
    """
    probe_df = dfs.get("fault_model_probe", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty:
        return pd.DataFrame([{
            "probe_with_simtime_rows": 0,
            "message": "no fault_model_probe records",
        }])

    lookup = _build_invocation_simtime_lookup(inv_df)
    return _rebuild_probe_simtime(probe_df, lookup)


def build_probe_fault_window_check(dfs: Dict[str, pd.DataFrame], fault_model) -> pd.DataFrame:
    """
    把 probe_with_simtime × fault_events 按 simtime ∈ [start, end] 关联。

    对每条 probe：
    - reason == "node_outage" 应至少有一个 fault_event 落在窗口内
    - reason == "network_degradation" 应至少有一个 fault_event 落在窗口内
    - reason == "normal" / "replica_error" 没有任何 fault_event 落在窗口内（replica_error 不依赖窗口）
    - window_match = True 表示故障窗口和 probe 判定一致
    """
    probe_with_sim = build_probe_with_simtime(dfs)
    if probe_with_sim.empty or fault_model is None:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing probe_with_simtime or fault_model",
        }])

    events = fault_model.events
    if not events:
        return pd.DataFrame()

    rows: List[dict] = []
    for _, p in probe_with_sim.iterrows():
        simtime = p.get("simtime")
        reason = p.get("reason")
        if pd.isna(simtime):
            rows.append({
                "function_name": p.get("function_name"),
                "request_id": p.get("request_id"),
                "replica_id": p.get("replica_id"),
                "reason": reason,
                "simtime": None,
                "in_window_faults": "",
                "expected_in_window": (reason in ("node_outage", "network_degradation")),
                "window_match": None,
            })
            continue

        # 找出 simtime 时刻作用于 node_name 的所有故障事件
        in_window = []
        for ev in events:
            if ev.target_node is not None and ev.target_node != p.get("node_name"):
                continue
            if ev.start_time <= simtime <= ev.end_time:
                in_window.append(ev.name)

        expected_in_window = (reason in ("node_outage", "network_degradation"))
        # replica_error 不依赖窗口；normal 应该窗口外
        if reason in ("node_outage", "network_degradation"):
            window_match = len(in_window) > 0
        elif reason == "normal":
            # normal 时应该没有任何 active fault（replica_error 也不算）
            window_match = len([w for w in in_window]) == 0
        else:  # replica_error
            window_match = True  # 不依赖窗口，不验证

        rows.append({
            "function_name": p.get("function_name"),
            "request_id": p.get("request_id"),
            "replica_id": p.get("replica_id"),
            "node_name": p.get("node_name"),
            "reason": reason,
            "simtime": simtime,
            "in_window_faults": ";".join(in_window),
            "expected_in_window": expected_in_window,
            "window_match": window_match,
        })

    return pd.DataFrame(rows)


def build_probe_invocation_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    probe × invocations 按 (function_name, replica_id) 分组后按顺序一一对应。

    probe 里的 final_duration（simulator 派发）和 invocations 里的 t_exec（faas-sim 实际记录）
    应该完全相等。
    """
    probe_df = build_probe_with_simtime(dfs)
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if probe_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing probe or invocations",
        }])

    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")
    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")

    rows: List[dict] = []
    for (fn, rep), probe_grp in probe_df.groupby(["function_name", "replica_id"], dropna=False):
        probe_sorted = probe_grp.sort_values("simtime").reset_index(drop=True)
        inv_grp = inv_df[(inv_df["function_name"] == fn) & (inv_df["replica_id"] == rep)].sort_values("t_start").reset_index(drop=True)
        n = min(len(probe_sorted), len(inv_grp))
        for i in range(n):
            p = probe_sorted.iloc[i]
            inv = inv_grp.iloc[i]
            duration_match = (
                pd.notna(inv["t_exec"])
                and abs(float(p["final_duration"]) - float(inv["t_exec"])) < 1e-6
            )
            rows.append({
                "function_name": fn,
                "request_id": p.get("request_id"),
                "replica_id": rep,
                "probe_simtime": float(p["simtime"]) if pd.notna(p.get("simtime")) else None,
                "probe_final_duration": float(p["final_duration"]),
                "probe_reason": p.get("reason"),
                "probe_success": bool(p["success"]),
                "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
                "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
                "duration_match": duration_match,
            })

    return pd.DataFrame(rows)


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

    # 给 probe 重建 simtime
    probe_with_sim_df = build_probe_with_simtime(dfs)
    probe_with_sim_path = output_dir / "probe_with_simtime.csv"
    probe_with_sim_df.to_csv(probe_with_sim_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", probe_with_sim_path)

    # probe × fault_events 窗口命中验证
    window_check_df = build_probe_fault_window_check(dfs, fault_model)
    window_check_path = output_dir / "probe_fault_window_check.csv"
    window_check_df.to_csv(window_check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", window_check_path)

    # probe × invocations 关联
    probe_inv_join_df = build_probe_invocation_join(dfs)
    probe_inv_join_path = output_dir / "probe_invocation_join.csv"
    probe_inv_join_df.to_csv(probe_inv_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", probe_inv_join_path)

    fault_summary_df = build_fault_summary(dfs)
    fault_summary_path = output_dir / "fault_model_summary.csv"
    fault_summary_df.to_csv(fault_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", fault_summary_path)

    fault_reason_df = build_fault_reason_distribution(dfs)
    fault_reason_path = output_dir / "fault_reason_distribution.csv"
    fault_reason_df.to_csv(fault_reason_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", fault_reason_path)

    dfs["fault_events"] = fault_event_df
    dfs["probe_with_simtime"] = probe_with_sim_df
    dfs["probe_fault_window_check"] = window_check_df
    dfs["probe_invocation_join"] = probe_inv_join_df
    dfs["fault_model_summary"] = fault_summary_df
    dfs["fault_reason_distribution"] = fault_reason_df

    return dfs