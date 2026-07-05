"""
文件作用：trace-driven 函数执行时间 Oracle。

该文件提供一个轻量级 TraceRuntimeOracle，用于从 CSV 文件读取函数执行时间轨迹，
并在函数调用时按顺序循环取样。

说明：
faas-sim 原始工程中不同版本对 trace/oracle 的封装不完全一致。
为了让样例更稳定，本文件实现一个独立、简单、可解释的 Oracle，
并在 simulator.py 中调用它。该实现不修改 faas-sim 内部逻辑。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TraceSample:
    """
    单条执行时间样本。

    字段：
    - function_name：函数名称；
    - sample_id：样本序号；
    - duration：执行时间，单位为仿真时间单位。
    """

    function_name: str
    sample_id: int
    duration: float


class TraceRuntimeOracle:
    """
    基于 CSV trace 的执行时间 Oracle。

    业务职责：
    - 从 CSV 中读取 function_name、sample_id、duration；
    - 按 function_name 建立样本序列；
    - 每次调用 sample(function_name) 时返回下一个样本；
    - 样本读完后循环使用，便于小样例稳定运行。
    """

    def __init__(self, trace_path: Path):
        """
        初始化 Oracle。

        参数：
        - trace_path：CSV trace 文件路径。
        """
        self.trace_path = Path(trace_path)
        self.samples: Dict[str, List[TraceSample]] = {}
        self.cursors: Dict[str, int] = {}

        self._load()

    def _load(self):
        """
        加载 trace CSV。
        """
        if not self.trace_path.exists():
            raise FileNotFoundError(f"trace file not found: {self.trace_path}")

        df = pd.read_csv(self.trace_path)

        required_columns = {"function_name", "sample_id", "duration"}
        missing = required_columns.difference(df.columns)
        if missing:
            raise ValueError(f"trace file missing columns: {sorted(missing)}")

        for row in df.itertuples(index=False):
            sample = TraceSample(
                function_name=str(row.function_name),
                sample_id=int(row.sample_id),
                duration=float(row.duration),
            )
            self.samples.setdefault(sample.function_name, []).append(sample)

        for function_name, values in self.samples.items():
            values.sort(key=lambda item: item.sample_id)
            self.cursors[function_name] = 0
            logger.info(
                "loaded trace samples function=%s count=%d avg_duration=%.4f",
                function_name,
                len(values),
                sum(item.duration for item in values) / len(values),
            )

    def sample(self, function_name: str) -> TraceSample:
        """
        为指定函数返回一个执行时间样本。

        参数：
        - function_name：函数名称。

        返回：
        - TraceSample：执行时间样本。

        取样策略：
        - 按 trace 中 sample_id 顺序取样；
        - 到达末尾后从头循环。
        """
        if function_name not in self.samples:
            raise KeyError(f"function {function_name} not found in trace oracle")

        values = self.samples[function_name]
        cursor = self.cursors[function_name]
        sample = values[cursor]

        self.cursors[function_name] = (cursor + 1) % len(values)

        return sample

    def summary_dataframe(self) -> pd.DataFrame:
        """
        生成 trace 自身的摘要表。
        """
        rows = []

        for function_name, values in self.samples.items():
            durations = [item.duration for item in values]
            rows.append({
                "function_name": function_name,
                "sample_count": len(durations),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
            })

        return pd.DataFrame(rows)
