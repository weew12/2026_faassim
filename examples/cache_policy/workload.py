"""
文件作用：请求 trace 读取与请求对象定义。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd


@dataclass(frozen=True)
class FunctionRequest:
    """
    函数请求。

    字段：
    - request_id：请求编号；
    - time：请求到达时间；
    - function_name：目标函数名称。
    """

    request_id: int
    time: float
    function_name: str


def load_request_trace(trace_path: Path) -> List[FunctionRequest]:
    """
    从 CSV 文件读取请求 trace。
    """
    trace_path = Path(trace_path)

    if not trace_path.exists():
        raise FileNotFoundError(f"request trace not found: {trace_path}")

    df = pd.read_csv(trace_path)

    required_columns = {"time", "function_name"}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"request trace missing columns: {sorted(missing)}")

    requests: List[FunctionRequest] = []

    for index, row in enumerate(df.sort_values("time").itertuples(index=False), start=1):
        requests.append(
            FunctionRequest(
                request_id=index,
                time=float(row.time),
                function_name=str(row.function_name),
            )
        )

    return requests
