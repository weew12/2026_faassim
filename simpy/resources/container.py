"""
SimPy 连续容量资源模型。

本文件实现 ``Container``，用于表达具有容量上限和当前水位的连续资源。``put``
增加水位，``get`` 消耗水位；当容量不足或剩余空间不足时，请求会进入等待队列。

在 faas-sim 语境中，该模型可用于表达：
- 缓存空间（init=可用容量，put=get=填充/淘汰）；
- 带宽令牌（每请求消耗 N 令牌，定时补充）；
- 资源预算（"还剩多少 CPU·s"这类累计量）；
- 其他任何"生产/消耗"关系的连续数量。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from simpy.core import BoundClass, Environment
from simpy.resources import base

# 类型别名：连续数量。允许 int（计数类）或 float（水位类）。
ContainerAmount = Union[int, float]


class ContainerPut(base.Put):
    """
    Container 的增加容量请求事件，用于向连续容量资源中加入指定数量。
    """

    def __init__(self, container: Container, amount: ContainerAmount):
        if amount <= 0:
            # amount 必须严格 > 0：传 0 没有业务意义，传负数会让水位下降但又走
            # "put" 的语义混乱，不如直接拒绝。
            raise ValueError(f'amount(={amount}) must be > 0.')
        # 字段：本次 Container put/get 操作涉及的连续数量。
        self.amount = amount

        # 父类 Put.__init__ 会完成：构造 Event、挂 put_queue、注册 _trigger_get 回调、
        # 调用 _trigger_put 立即尝试满足。Container 的 _do_put 看到 amount 后判断
        # 剩余容量是否足够。
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
    连续容量资源。

    它维护 ``capacity`` 与当前水位 ``_level``，支持 ``put`` 增加水位、``get``
    减少水位，并在条件不满足时让请求排队。默认使用 ``list`` 作为 put/get 队列，
    因此请求按 FIFO 处理；如需优先级请自行继承并实现排序队列。
    """

    def __init__(
        self,
        env: Environment,
        capacity: ContainerAmount = float('inf'),
        init: ContainerAmount = 0,
    ):
        if capacity <= 0:
            # 容量 <= 0 没法装东西，拒绝构造。
            raise ValueError('"capacity" must be > 0.')
        if init < 0:
            # 初始水位负数无意义。
            raise ValueError('"init" must be >= 0.')
        if init > capacity:
            # 初始水位超过容量违反不变量。
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
        # 仅静态类型检查分支：声明带参 put/get 的签名，方便 IDE 提示 amount 参数。

        def put(  # type: ignore[override]
            self, amount: ContainerAmount
        ) -> ContainerPut:
            """
            创建向容器增加 ``amount`` 水位的事件。

            事件可能立即成功，也可能因剩余容量不足而排队等待。
            """
            return ContainerPut(self, amount)

        def get(  # type: ignore[override]
            self, amount: ContainerAmount
        ) -> ContainerGet:
            """
            创建从容器消耗 ``amount`` 水位的事件。

            事件可能立即成功，也可能因当前水位不足而排队等待。
            """
            return ContainerGet(self, amount)

    else:
        # 运行时：通过 BoundClass 把带参的 ContainerPut / ContainerGet 绑定到实例。
        # 这样 ``env.Container(...)`` 拿到实例后可以直接 ``c.put(5)``，等价于
        # ``ContainerPut(c, 5)``。
        put = BoundClass(ContainerPut)
        get = BoundClass(ContainerGet)

    def _do_put(self, event: ContainerPut) -> Optional[bool]:
        # 容量判断：剩余空间 ``capacity - level`` 必须 ≥ amount 才能装下。
        if self._capacity - self._level >= event.amount:
            self._level += event.amount
            event.succeed()
            # 返回 True：本次 put 不改变其它 put 请求的可满足性，可以让循环继续。
            return True
        else:
            # 容量不足，请求留在 put_queue 中等待后续 _trigger_put 重新检查。
            return None

    def _do_get(self, event: ContainerGet) -> Optional[bool]:
        # 容量判断：当前水位必须 ≥ amount 才能消耗。
        if self._level >= event.amount:
            self._level -= event.amount
            event.succeed()
            return True
        else:
            # 水位不足，请求留在 get_queue 中等待。
            return None
