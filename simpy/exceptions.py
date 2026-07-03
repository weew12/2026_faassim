"""
SimPy 异常模型。

本文件定义 SimPy 运行时使用的基础异常。``Interrupt`` 用于在仿真进程等待事件时向
该进程注入中断，例如抢占式资源剥夺、外部停止或过程取消；``SimPyException`` 作为
SimPy 异常层次的基础类型，便于上层代码统一捕获仿真运行异常。
"""

from __future__ import annotations

from typing import Any, Optional


class SimPyException(Exception):
    """
    SimPy 异常基类，用于表示由仿真框架自身产生的异常。
    """


class Interrupt(SimPyException):
    """
    进程中断异常。Process 收到 Interruption 时会把该异常抛入生成器，业务进程可捕获后执行清理或重试逻辑。
    """

    def __init__(self, cause: Optional[Any]):
        super().__init__(cause)

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.cause!r})'

    @property
    def cause(self) -> Optional[Any]:
        """
        读取进程被中断的业务原因。
        """
        return self.args[0]
