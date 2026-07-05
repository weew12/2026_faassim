"""
文件作用：读取论文实验输入数据。
"""

from pathlib import Path
from typing import Dict, List

import pandas as pd

from models import (
    ExperimentCase,
    FunctionProfile,
    NodeState,
    WorkloadEvent,
)


def _to_bool(value) -> bool:
    """
    兼容 CSV 布尔值。
    """
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_function_profiles(path: Path) -> Dict[str, FunctionProfile]:
    """
    读取函数画像。
    """
    df = pd.read_csv(Path(path))
    required = {
        "function_name",
        "cold_start_duration",
        "warm_duration",
        "image_pull_duration",
        "data_fetch_duration",
        "memory_units",
        "replica_capacity_rps",
        "cpu_demand",
        "memory_demand",
        "preferred_zone",
        "require_accel",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"function_profile.csv missing columns: {sorted(missing)}")

    profiles: Dict[str, FunctionProfile] = {}
    for row in df.itertuples(index=False):
        profile = FunctionProfile(
            function_name=str(row.function_name),
            cold_start_duration=float(row.cold_start_duration),
            warm_duration=float(row.warm_duration),
            image_pull_duration=float(row.image_pull_duration),
            data_fetch_duration=float(row.data_fetch_duration),
            memory_units=int(row.memory_units),
            replica_capacity_rps=float(row.replica_capacity_rps),
            cpu_demand=float(row.cpu_demand),
            memory_demand=float(row.memory_demand),
            preferred_zone=str(row.preferred_zone),
            require_accel=_to_bool(row.require_accel),
        )
        profiles[profile.function_name] = profile

    return profiles


def load_nodes(path: Path) -> Dict[str, NodeState]:
    """
    读取节点状态。
    """
    df = pd.read_csv(Path(path))
    required = {
        "node_name",
        "edge_zone",
        "cpu_free",
        "memory_free",
        "current_load",
        "network_latency_ms",
        "supports_accel",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"node_state.csv missing columns: {sorted(missing)}")

    nodes: Dict[str, NodeState] = {}
    for row in df.itertuples(index=False):
        node = NodeState(
            node_name=str(row.node_name),
            edge_zone=str(row.edge_zone),
            cpu_free=float(row.cpu_free),
            memory_free=float(row.memory_free),
            current_load=float(row.current_load),
            network_latency_ms=float(row.network_latency_ms),
            supports_accel=_to_bool(row.supports_accel),
        )
        nodes[node.node_name] = node

    return nodes


def load_workload(path: Path) -> List[WorkloadEvent]:
    """
    读取请求 trace。
    """
    df = pd.read_csv(Path(path))
    required = {"request_id", "time", "function_name", "source_zone", "phase"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"workload_trace.csv missing columns: {sorted(missing)}")

    events: List[WorkloadEvent] = []
    for row in df.sort_values("time").itertuples(index=False):
        events.append(
            WorkloadEvent(
                request_id=int(row.request_id),
                time=float(row.time),
                function_name=str(row.function_name),
                source_zone=str(row.source_zone),
                phase=str(row.phase),
            )
        )

    return events


def load_experiment_cases(path: Path) -> List[ExperimentCase]:
    """
    读取实验 case 配置。
    """
    df = pd.read_csv(Path(path))
    required = {
        "case_id",
        "policy_name",
        "use_cache_decision",
        "use_load_scaling",
        "use_cache_aware_scheduler",
        "cache_capacity_units",
        "target_utilization",
        "cache_utility_threshold",
        "base_keep_alive",
        "max_keep_alive",
        "description",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"experiment_cases.csv missing columns: {sorted(missing)}")

    cases: List[ExperimentCase] = []
    for row in df.itertuples(index=False):
        cases.append(
            ExperimentCase(
                case_id=str(row.case_id),
                policy_name=str(row.policy_name),
                use_cache_decision=_to_bool(row.use_cache_decision),
                use_load_scaling=_to_bool(row.use_load_scaling),
                use_cache_aware_scheduler=_to_bool(row.use_cache_aware_scheduler),
                cache_capacity_units=int(row.cache_capacity_units),
                target_utilization=float(row.target_utilization),
                cache_utility_threshold=float(row.cache_utility_threshold),
                base_keep_alive=float(row.base_keep_alive),
                max_keep_alive=float(row.max_keep_alive),
                description=str(row.description),
            )
        )

    return cases
