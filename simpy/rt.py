"""
SimPy 实时仿真环境。

本文件在普通离散事件环境基础上加入墙钟时间同步能力。``RealtimeEnvironment`` 会按照
指定 ``factor`` 将仿真时间映射到真实时间，适用于需要把仿真与外部系统、人工观察或
在线控制循环对齐的场景。

faas-sim 默认采用普通离散事件仿真；若后续做数字孪生或在线协同仿真，可参考该环境
实现真实时间同步。
"""

from time import monotonic, sleep

from simpy.core import EmptySchedule, Environment, Infinity, SimTime


class RealtimeEnvironment(Environment):
    """
    实时环境。它继承 Environment，并在 step 前等待墙钟时间，使仿真时间按 factor 与真实时间保持同步。
    """

    def __init__(
        self,
        initial_time: SimTime = 0,
        factor: float = 1.0,
        strict: bool = True,
    ):
        Environment.__init__(self, initial_time)

        # 字段：实时环境同步时的仿真起始时间。
        self.env_start = initial_time
        # 字段：实时环境同步时的真实墙钟起始时间。
        self.real_start = monotonic()
        # 字段：仿真时间到真实秒数的换算因子。
        self._factor = factor
        # 字段：是否在仿真落后墙钟时间过多时抛出错误。
        self._strict = strict

    @property
    def factor(self) -> float:
        """
        返回一个仿真时间单位对应的真实秒数。
        """
        return self._factor

    @property
    def strict(self) -> bool:
        """
        返回是否启用严格实时模式。
        """
        return self._strict

    def sync(self) -> None:
        """
        把当前仿真时间与当前真实时间重新对齐。
        """
        self.real_start = monotonic()

    def step(self) -> None:
        """
        在执行下一个离散事件前等待对应墙钟时间，必要时检查仿真是否落后过多。
        """
        evt_time = self.peek()

        if evt_time is Infinity:
            raise EmptySchedule

        real_time = self.real_start + (evt_time - self.env_start) * self.factor

        if self.strict and monotonic() - real_time > self.factor:
            delta = monotonic() - real_time
            raise RuntimeError(f'Simulation too slow for real time ({delta:.3f}s).')

        while True:
            delta = real_time - monotonic()
            if delta <= 0:
                break
            sleep(delta)

        Environment.step(self)
