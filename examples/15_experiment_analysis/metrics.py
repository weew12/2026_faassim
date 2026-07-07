"""
文件作用：单次实验指标计算。

该文件把不同 CSV 中的信息统一压缩为一行 run-level 结果，
便于后续批量汇总和策略对比。
"""

from typing import Dict, Any

import pandas as pd

from loaders import RunData


def first_value(df: pd.DataFrame, column: str, default=None):
    """
    读取 DataFrame 第一行指定列。
    """
    if df.empty or column not in df.columns:
        return default
    return df[column].iloc[0]


def build_run_metrics(run: RunData) -> Dict[str, Any]:
    """
    为单个 run 生成标准化指标。
    """
    case_df = run.tables.get("case_result.csv", pd.DataFrame())
    probe_df = run.tables.get("batch_invoke_probe.csv", pd.DataFrame())
    invocation_df = run.tables.get("invocations.csv", pd.DataFrame())
    schedule_df = run.tables.get("schedule.csv", pd.DataFrame())
    flow_df = run.tables.get("flow.csv", pd.DataFrame())
    replica_df = run.tables.get("replica_deployment.csv", pd.DataFrame())

    row: Dict[str, Any] = {
        "run_id": run.run_id,
        "run_dir": str(run.run_dir),
        "case_id": first_value(case_df, "case_id", run.run_id),
        "policy": first_value(case_df, "policy", infer_policy_from_run_id(run.run_id)),
        "workload": first_value(case_df, "workload", infer_workload_from_run_id(run.run_id)),
        "seed": first_value(case_df, "seed", infer_seed_from_run_id(run.run_id)),
        "rps": first_value(case_df, "rps", None),
        "max_requests": first_value(case_df, "max_requests", None),
        # 从 case_result.csv 取 scheduled_node（14 已经预聚合为单值字符串）
        # 用于 paper highlight 的 high_capacity_hit_ratio 统计
        "scheduled_node": first_value(case_df, "scheduled_node", None),
    }

    row.update(compute_probe_metrics(probe_df))
    row.update(compute_invocation_metrics(invocation_df))
    row.update(compute_schedule_metrics(schedule_df))
    row.update(compute_flow_metrics(flow_df))
    row.update(compute_replica_metrics(replica_df))

    return row


def compute_probe_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算 batch_invoke_probe 指标。
    """
    result = {
        "probe_events": len(df),
    }

    if not df.empty and "duration" in df.columns:
        result.update({
            "probe_avg_duration": float(df["duration"].mean()),
            "probe_min_duration": float(df["duration"].min()),
            "probe_max_duration": float(df["duration"].max()),
            "probe_p95_duration": float(df["duration"].quantile(0.95)),
        })

    return result


def compute_invocation_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算 invocations 指标。
    """
    result = {
        "invocation_events": len(df),
    }

    if not df.empty and "duration" in df.columns:
        result.update({
            "invocation_avg_duration": float(df["duration"].mean()),
            "invocation_max_duration": float(df["duration"].max()),
        })

    if not df.empty and "function_name" in df.columns:
        result["function_count"] = int(df["function_name"].nunique())

    return result


def compute_schedule_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算 schedule 指标。
    """
    result = {
        "schedule_events": len(df),
    }

    if not df.empty and "node_name" in df.columns:
        non_null_nodes = df["node_name"].dropna()
        result["scheduled_node_count"] = int(non_null_nodes.nunique())
        result["scheduled_nodes"] = ";".join(sorted(non_null_nodes.astype(str).unique()))

    if not df.empty and "successful" in df.columns:
        successful = df["successful"].dropna()
        if len(successful) > 0:
            result["schedule_success_rate"] = float(successful.astype(bool).mean())

    return result


def compute_flow_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算 flow 指标。
    """
    result = {
        "flow_events": len(df),
    }

    if not df.empty and "bytes" in df.columns:
        result["flow_total_bytes"] = int(df["bytes"].sum())

    if not df.empty and "duration" in df.columns:
        result["flow_total_duration"] = float(df["duration"].sum())
        result["flow_avg_duration"] = float(df["duration"].mean())

    return result


def compute_replica_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算 replica_deployment 指标。
    """
    result = {
        "replica_deployment_events": len(df),
    }

    if not df.empty and "node_name" in df.columns:
        non_null_nodes = df["node_name"].dropna()
        result["replica_node_count"] = int(non_null_nodes.nunique())

    return result


def infer_policy_from_run_id(run_id: str):
    """
    从 run_id 中推断策略名。
    """
    parts = run_id.split("__")
    return parts[0] if parts else run_id


def infer_workload_from_run_id(run_id: str):
    """
    从 run_id 中推断负载名。
    """
    parts = run_id.split("__")
    if len(parts) >= 2:
        return parts[1]
    return None


def infer_seed_from_run_id(run_id: str):
    """
    从 run_id 中推断随机种子。
    """
    parts = run_id.split("__")
    for part in parts:
        if part.startswith("seed_"):
            try:
                return int(part.replace("seed_", ""))
            except Exception:
                return None
    return None
