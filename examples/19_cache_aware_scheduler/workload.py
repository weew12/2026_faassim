"""
文件作用：缓存感知调度样例的 workload 读取。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd


@dataclass(frozen=True)
class SchedulerRequest:
    """
    请求记录。

    字段：
    - request_id：请求编号；
    - function_name：目标函数；
    - arrival_time：到达时间。
    """

    request_id: int
    function_name: str
    arrival_time: float


def load_workload(workload_path: Path) -> List[SchedulerRequest]:
    """
    从 CSV 读取请求序列。
    """
    workload_path = Path(workload_path)

    if not workload_path.exists():
        raise FileNotFoundError(f"workload not found: {workload_path}")

    df = pd.read_csv(workload_path)

    required_columns = {"request_id", "function_name", "arrival_time"}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"workload missing columns: {sorted(missing)}")

    requests: List[SchedulerRequest] = []

    for row in df.sort_values("arrival_time").itertuples(index=False):
        requests.append(
            SchedulerRequest(
                request_id=int(row.request_id),
                function_name=str(row.function_name),
                arrival_time=float(row.arrival_time),
            )
        )

    return requests
