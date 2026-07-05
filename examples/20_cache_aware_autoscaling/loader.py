"""
文件作用：读取函数状态时间序列。
"""

from pathlib import Path
from typing import List

import pandas as pd

from models import FunctionState


def load_function_states(input_path: Path) -> List[FunctionState]:
    """
    从 CSV 读取函数状态时间序列。
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"function state timeseries not found: {input_path}")

    df = pd.read_csv(input_path)

    required_columns = {
        "time",
        "function_name",
        "current_replicas",
        "warm_replicas",
        "n_req",
        "request_rate",
        "avg_response_time",
        "avg_cold_start",
        "cold_miss_count",
        "memory_units",
        "replica_capacity_rps",
        "in_flight_requests",
        "last_seen_age",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"function state timeseries missing columns: {sorted(missing)}")

    states: List[FunctionState] = []

    for row in df.sort_values(["time", "function_name"]).itertuples(index=False):
        states.append(
            FunctionState(
                time=float(row.time),
                function_name=str(row.function_name),
                current_replicas=int(row.current_replicas),
                warm_replicas=int(row.warm_replicas),
                n_req=int(row.n_req),
                request_rate=float(row.request_rate),
                avg_response_time=float(row.avg_response_time),
                avg_cold_start=float(row.avg_cold_start),
                cold_miss_count=int(row.cold_miss_count),
                memory_units=int(row.memory_units),
                replica_capacity_rps=float(row.replica_capacity_rps),
                in_flight_requests=int(row.in_flight_requests),
                last_seen_age=float(row.last_seen_age),
            )
        )

    return states
