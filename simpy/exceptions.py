"""
SimPy 异常模型。

本文件定义 SimPy 运行时使用的基础异常。规模虽小，但有两个关键点：

- ``Interrupt`` —— 进程被中断的统一入口。被中断时，``Process._resume`` 会把该异常
  作为 ``throw`` 注入生成器，业务进程可捕获后执行清理或重试逻辑。
- ``SimPyException`` —— SimPy 异常的基类。所有仿真框架自身抛出的异常都可被它
  统一捕获。

faas-sim 衔接：
- ``PreemptiveResource`` 抢占时通过 ``Interrupt(Preempted(...))`` 中断低优先级副本；
- ``util.subscribe_at`` 在被订阅事件触发时通过 ``Interrupt((signaller, result))``
  唤醒订阅者；
- 业务进程通常用 ``except simpy.Interrupt as i: i.cause`` 拿到中断原因对象。
"""

from __future__ import annotations

from typing import Any, Optional


class SimPyException(Exception):
    """
    SimPy 异常基类，用于表示由仿真框架自身产生的异常。

    业务层可以用 ``except SimPyException:`` 一次性捕获所有 SimPy 内部异常，而把
    Python 标准异常（如 ``ValueError``、``RuntimeError``）留给业务代码自身处理。
    faas-sim 中常用于隔离"仿真框架错误"与"用户业务错误"。
    """


class Interrupt(SimPyException):
    """
    进程中断异常。

    ``Process.interrupt(cause)`` 触发后，事件系统会创建一个 ``Interruption`` 事件，
    在下一轮 ``step`` 时把 ``Interrupt(cause)`` 作为 ``throw`` 注入到目标生成器中，
    业务进程可在 ``except Interrupt as i:`` 处捕获并通过 ``i.cause`` 读取原因对象。

    ``cause`` 可以是任意业务对象：
    - 抢占场景：``Preempted(by=..., usage_since=..., resource=...)``
    - 订阅场景：``(signaller_event, signaller_result)`` 元组
    - faas-sim 副本被取消：自定义字符串或业务对象
    """

    def __init__(self, cause: Optional[Any]):
        # 直接把 cause 写入 args[0]，SimPyException/Exception 都会自动调用 __str__，
        # 这里不需要额外保存字段——通过下面的 ``cause`` property 暴露。
        super().__init__(cause)

    def __str__(self) -> str:
        # 重写 __str__，让 traceback/日志直接显示 ``Interrupt(<cause repr>)`` 而
        # 不是默认的 ``Interrupt(cause)``，调试时更容易定位中断来源。
        return f'{self.__class__.__name__}({self.cause!r})'

    @property
    def cause(self) -> Optional[Any]:
        """
        读取进程被中断的业务原因。

        注意：Interrupt 实例本身**不可哈希**（args 不参与哈希），但 ``cause`` 对象
        可以是任意类型，业务层可自由判断 / 序列化。
        """
        return self.args[0]