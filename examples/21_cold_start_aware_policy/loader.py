"""
文件作用：读取函数画像和请求 trace。
"""

from pathlib import Path
from typing import Dict, List

import pandas as pd

from models import FunctionProfile, RequestEvent


def load_function_profiles(path: Path) -> Dict[str, FunctionProfile]:
    """
    读取函数画像。
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"function profile not found: {path}")

    df = pd.read_csv(path)

    required_columns = {
        "function_name",
        "cold_start_duration",
        "warm_duration",
        "memory_units",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"function profile missing columns: {sorted(missing)}")

    profiles: Dict[str, FunctionProfile] = {}

    for row in df.itertuples(index=False):
        profile = FunctionProfile(
            function_name=str(row.function_name),
            cold_start_duration=float(row.cold_start_duration),
            warm_duration=float(row.warm_duration),
            memory_units=int(row.memory_units),
        )
        profiles[profile.function_name] = profile

    return profiles


def load_request_trace(path: Path) -> List[RequestEvent]:
    """
    读取请求 trace。
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"request trace not found: {path}")

    df = pd.read_csv(path)

    required_columns = {"time", "function_name"}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"request trace missing columns: {sorted(missing)}")

    requests: List[RequestEvent] = []

    for index, row in enumerate(df.sort_values("time").itertuples(index=False), start=1):
        requests.append(
            RequestEvent(
                request_id=index,
                time=float(row.time),
                function_name=str(row.function_name),
            )
        )

    return requests
