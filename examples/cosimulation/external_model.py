"""
文件作用：外部环境 trace 读取与阶段查询。

该文件把外部环境变化抽象为一组按时间排列的 ExternalPhase。
在更复杂的协同仿真中，这里可以替换为：
- 外部网络仿真器；
- 强化学习控制器；
- 真实监控 trace；
- 其他进程或服务通过文件/socket/API 提供的动态信号。
"""

from pathlib import Path
from typing import List, Optional

import pandas as pd

from context import ExternalPhase


class ExternalEnvironmentTrace:
    """
    外部环境 trace。

    职责：
    - 从 CSV 读取外部阶段；
    - 按时间查询当前阶段；
    - 提供阶段总时长和 DataFrame 导出。
    """

    def __init__(self, trace_path: Path):
        """
        初始化外部 trace。
        """
        self.trace_path = Path(trace_path)
        self.phases: List[ExternalPhase] = []
        self._load()

    def _load(self):
        """
        加载 CSV trace。
        """
        if not self.trace_path.exists():
            raise FileNotFoundError(f"external trace not found: {self.trace_path}")

        df = pd.read_csv(self.trace_path)

        required_columns = {
            "phase_name",
            "start_time",
            "duration",
            "rps",
            "runtime_factor",
            "network_delay",
            "controller_action",
            "description",
        }
        missing = required_columns.difference(df.columns)
        if missing:
            raise ValueError(f"external trace missing columns: {sorted(missing)}")

        phases: List[ExternalPhase] = []
        for row in df.itertuples(index=False):
            phases.append(
                ExternalPhase(
                    phase_name=str(row.phase_name),
                    start_time=float(row.start_time),
                    duration=float(row.duration),
                    rps=float(row.rps),
                    runtime_factor=float(row.runtime_factor),
                    network_delay=float(row.network_delay),
                    controller_action=str(row.controller_action),
                    description=str(row.description),
                )
            )

        self.phases = sorted(phases, key=lambda item: item.start_time)

    def phase_at(self, now: float) -> Optional[ExternalPhase]:
        """
        查询指定仿真时间对应的外部阶段。
        """
        for phase in self.phases:
            if phase.start_time <= now < phase.end_time:
                return phase
        return None

    def total_duration(self) -> float:
        """
        返回外部 trace 覆盖的总时长。
        """
        if not self.phases:
            return 0.0
        return max(phase.end_time for phase in self.phases)

    def to_dataframe(self) -> pd.DataFrame:
        """
        返回 trace DataFrame。
        """
        return pd.DataFrame([phase.__dict__ for phase in self.phases])
