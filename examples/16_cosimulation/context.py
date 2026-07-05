"""
文件作用：协同仿真上下文。

CosimulationContext 是 faas-sim 与外部模型之间共享的轻量状态对象。
外部控制器根据 trace 更新当前环境状态，函数模拟器在 invoke 阶段读取该状态，
从而让外部环境影响函数执行过程。
"""

from dataclasses import dataclass


@dataclass
class ExternalPhase:
    """
    外部环境阶段。

    字段：
    - phase_name：阶段名称；
    - start_time：阶段开始时间；
    - duration：阶段持续时间；
    - rps：该阶段请求速率；
    - runtime_factor：函数基础执行时间放大系数；
    - network_delay：额外网络延迟；
    - controller_action：外部控制器动作；
    - description：阶段说明。
    """

    phase_name: str
    start_time: float
    duration: float
    rps: float
    runtime_factor: float
    network_delay: float
    controller_action: str
    description: str

    @property
    def end_time(self) -> float:
        """
        返回阶段结束时间。
        """
        return self.start_time + self.duration


class CosimulationContext:
    """
    协同仿真共享上下文。

    该对象由外部控制器更新，由函数模拟器读取。
    """

    def __init__(self):
        """
        初始化上下文。
        """
        self.phase_name = "uninitialized"
        self.runtime_factor = 1.0
        self.network_delay = 0.0
        self.controller_action = "observe"
        self.description = ""

    def update_from_phase(self, phase: ExternalPhase):
        """
        根据外部阶段更新共享上下文。
        """
        self.phase_name = phase.phase_name
        self.runtime_factor = phase.runtime_factor
        self.network_delay = phase.network_delay
        self.controller_action = phase.controller_action
        self.description = phase.description

    def snapshot(self) -> dict:
        """
        返回当前上下文快照。
        """
        return {
            "phase_name": self.phase_name,
            "runtime_factor": self.runtime_factor,
            "network_delay": self.network_delay,
            "controller_action": self.controller_action,
            "description": self.description,
        }
