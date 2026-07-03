"""
SimPy 连续容量资源模型。

本文件实现 ``Container``，用于表达具有容量上限和当前水位的连续资源。``put`` 增加
水位，``get`` 消耗水位；当容量不足或剩余空间不足时，请求会进入等待队列。

在 faas-sim 语境中，该模型可用于表达缓存空间、带宽令牌、资源预算等连续数量，适合
需要“生产/消耗”关系的仿真场景。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from simpy.core import BoundClass, Environment
from simpy.resources import base

ContainerAmount = Union[int, float]


class ContainerPut(base.Put):
    """
    Container 的增加容量请求事件，用于向连续容量资源中加入指定数量。
    """

    def __init__(self, container: Container, amount: ContainerAmount):
        if amount <= 0:
            raise ValueError(f'amount(={amount}) must be > 0.')
        # 字段：本次 Container put/get 操作涉及的连续数量。
        self.amount = amount

        super().__init__(container)


class ContainerGet(base.Get):
    """
    Container 的消耗容量请求事件，用于从连续容量资源中取出指定数量。
    """

    def __init__(self, container: Container, amount: ContainerAmount):
        if amount <= 0:
            raise ValueError(f'amount(={amount}) must be > 0.')
        self.amount = amount

        super().__init__(container)


class Container(base.BaseResource):
    """
    连续容量资源。它维护 capacity 与当前 level，支持 put 增加水位、get 减少水位，并在条件不满足时让请求排队。
    """

    def __init__(
        self,
        env: Environment,
        capacity: ContainerAmount = float('inf'),
        init: ContainerAmount = 0,
    ):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')
        if init < 0:
            raise ValueError('"init" must be >= 0.')
        if init > capacity:
            raise ValueError('"init" must be <= "capacity".')

        super().__init__(env, capacity)

        # 字段：Container 当前水位。
        self._level = init

    @property
    def level(self) -> ContainerAmount:
        """
        返回当前水位。
        """
        return self._level

    if TYPE_CHECKING:

        def put(  # type: ignore[override]
            self, amount: ContainerAmount
        ) -> ContainerPut:
            """
            执行 ``Container.put`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return ContainerPut(self, amount)

        def get(  # type: ignore[override]
            self, amount: ContainerAmount
        ) -> ContainerGet:
            """
            执行 ``Container.get`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return ContainerGet(self, amount)

    else:
        put = BoundClass(ContainerPut)
        get = BoundClass(ContainerGet)

    def _do_put(self, event: ContainerPut) -> Optional[bool]:
        if self._capacity - self._level >= event.amount:
            self._level += event.amount
            event.succeed()
            return True
        else:
            return None

    def _do_get(self, event: ContainerGet) -> Optional[bool]:
        if self._level >= event.amount:
            self._level -= event.amount
            event.succeed()
            return True
        else:
            return None
