"""
文件作用：函数画像快照读取。

该文件把 CSV 中的函数运行状态转换为 FunctionProfile 对象。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd


@dataclass(frozen=True)
class FunctionProfile:
    """
    函数画像。

    字段：
    - function_name：函数名称；
    - current_replicas：当前副本数；
    - warm_replicas：当前 warm 副本数；
    - n_req：观察窗口内请求数；
    - cold_miss_count：观察窗口内冷启动缺失次数；
    - avg_cold_start：平均冷启动耗时；
    - warm_duration：热路径执行耗时；
    - memory_units：缓存该函数实例占用的抽象资源单位；
    - last_seen_age：距离最近一次请求的时间；
    - in_flight_requests：正在执行的请求数；
    - request_rate：请求速率。
    """

    function_name: str
    current_replicas: int
    warm_replicas: int
    n_req: int
    cold_miss_count: int
    avg_cold_start: float
    warm_duration: float
    memory_units: int
    last_seen_age: float
    in_flight_requests: int
    request_rate: float


def load_profiles(profile_path: Path) -> List[FunctionProfile]:
    """
    从 CSV 文件读取函数画像快照。
    """
    profile_path = Path(profile_path)

    if not profile_path.exists():
        raise FileNotFoundError(f"profile snapshot not found: {profile_path}")

    df = pd.read_csv(profile_path)

    required_columns = {
        "function_name",
        "current_replicas",
        "warm_replicas",
        "n_req",
        "cold_miss_count",
        "avg_cold_start",
        "warm_duration",
        "memory_units",
        "last_seen_age",
        "in_flight_requests",
        "request_rate",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"profile snapshot missing columns: {sorted(missing)}")

    profiles: List[FunctionProfile] = []

    for row in df.itertuples(index=False):
        profiles.append(
            FunctionProfile(
                function_name=str(row.function_name),
                current_replicas=int(row.current_replicas),
                warm_replicas=int(row.warm_replicas),
                n_req=int(row.n_req),
                cold_miss_count=int(row.cold_miss_count),
                avg_cold_start=float(row.avg_cold_start),
                warm_duration=float(row.warm_duration),
                memory_units=int(row.memory_units),
                last_seen_age=float(row.last_seen_age),
                in_flight_requests=int(row.in_flight_requests),
                request_rate=float(row.request_rate),
            )
        )

    return profiles
