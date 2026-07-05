"""
文件作用：读取节点状态、函数画像、缓存快照和请求 trace。
"""

from pathlib import Path
from typing import Dict, List

import pandas as pd

from models import (
    CacheEntry,
    FunctionProfile,
    NodeState,
    RequestEvent,
)


def _to_bool(value) -> bool:
    """
    兼容 CSV 中的布尔字段。
    """
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


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
        raise ValueError(f"node state missing columns: {sorted(missing)}")

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


def load_profiles(path: Path) -> Dict[str, FunctionProfile]:
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
        "memory_demand",
        "cpu_demand",
        "preferred_zone",
        "require_accel",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"function profile missing columns: {sorted(missing)}")

    profiles: Dict[str, FunctionProfile] = {}
    for row in df.itertuples(index=False):
        profile = FunctionProfile(
            function_name=str(row.function_name),
            cold_start_duration=float(row.cold_start_duration),
            warm_duration=float(row.warm_duration),
            image_pull_duration=float(row.image_pull_duration),
            data_fetch_duration=float(row.data_fetch_duration),
            memory_demand=float(row.memory_demand),
            cpu_demand=float(row.cpu_demand),
            preferred_zone=str(row.preferred_zone),
            require_accel=_to_bool(row.require_accel),
        )
        profiles[profile.function_name] = profile

    return profiles


def load_cache_entries(path: Path) -> List[CacheEntry]:
    """
    读取缓存快照。
    """
    df = pd.read_csv(Path(path))
    required = {"cache_type", "cache_key", "node_name", "cached", "freshness"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"cache state missing columns: {sorted(missing)}")

    entries: List[CacheEntry] = []
    for row in df.itertuples(index=False):
        entries.append(
            CacheEntry(
                cache_type=str(row.cache_type),
                cache_key=str(row.cache_key),
                node_name=str(row.node_name),
                cached=_to_bool(row.cached),
                freshness=float(row.freshness),
            )
        )

    return entries


def load_requests(path: Path) -> List[RequestEvent]:
    """
    读取请求 trace。
    """
    df = pd.read_csv(Path(path))
    required = {"request_id", "time", "function_name", "source_zone"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"request trace missing columns: {sorted(missing)}")

    requests: List[RequestEvent] = []
    for row in df.sort_values("time").itertuples(index=False):
        requests.append(
            RequestEvent(
                request_id=int(row.request_id),
                time=float(row.time),
                function_name=str(row.function_name),
                source_zone=str(row.source_zone),
            )
        )

    return requests
