"""
SimPy 离散对象存储与队列模型。

本文件实现面向对象项的队列资源。``Store`` 按 FIFO 保存对象；``PriorityStore`` 使用
堆按优先级弹出对象；``FilterStore`` 允许 get 请求指定过滤条件，只取满足条件的对象。

在 faas-sim 中，这类资源适合用于建模请求队列、消息队列、任务缓冲区和负载均衡器
内部等待队列。
"""

from __future__ import annotations

from heapq import heappop, heappush
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    NamedTuple,
    Optional,
    Union,
)

from simpy.core import BoundClass, Environment
from simpy.resources import base


class StorePut(base.Put):
    """
    Store 的入队事件。它把对象项放入离散对象队列。
    """

    def __init__(self, store: Store, item: Any):
        # 字段：Store put 请求携带的待入队对象。
        self.item = item
        super().__init__(store)


class StoreGet(base.Get):
    """
    Store 的出队事件。它从离散对象队列中取出一个对象项。
    """


class FilterStoreGet(StoreGet):
    """
    带过滤条件的出队事件。它只在队列中存在满足 filter 函数的对象时成功。
    """

    def __init__(
        self,
        resource: FilterStore,
        filter: Callable[[Any], bool] = lambda item: True,
    ):
        # 字段：FilterStoreGet 用于选择对象的过滤函数。
        self.filter = filter
        super().__init__(resource)


class Store(base.BaseResource):
    """
    FIFO 离散对象队列。put 添加对象，get 取出最早进入的对象，容量满或队列空时请求会等待。
    """

    def __init__(self, env: Environment, capacity: Union[float, int] = float('inf')):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')

        super().__init__(env, capacity)

        # 字段：Store 当前保存的对象列表或堆。
        self.items: List[Any] = []

    if TYPE_CHECKING:

        def put(  # type: ignore[override]
            self, item: Any
        ) -> StorePut:
            """
            执行 ``Store.put`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return StorePut(self, item)

        def get(self) -> StoreGet:  # type: ignore[override]
            """
            执行 ``Store.get`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return StoreGet(self)

    else:
        put = BoundClass(StorePut)
        get = BoundClass(StoreGet)

    def _do_put(self, event: StorePut) -> Optional[bool]:
        if len(self.items) < self._capacity:
            self.items.append(event.item)
            event.succeed()
        return None

    def _do_get(self, event: StoreGet) -> Optional[bool]:
        if self.items:
            event.succeed(self.items.pop(0))
        return None


class PriorityItem(NamedTuple):
    """
    优先级对象包装器。它把 priority 与 item 绑定，并只基于 priority 比较大小，便于 PriorityStore 使用堆排序。
    """

    priority: Any

    item: Any

    def __lt__(  # type: ignore[override]
        self, other: PriorityItem
    ) -> bool:
        return self.priority < other.priority


class PriorityStore(Store):
    """
    优先级对象队列。队列中的对象按堆结构排序，get 每次返回优先级最小的对象。
    """

    def _do_put(self, event: StorePut) -> Optional[bool]:
        if len(self.items) < self._capacity:
            heappush(self.items, event.item)
            event.succeed()
        return None

    def _do_get(self, event: StoreGet) -> Optional[bool]:
        if self.items:
            event.succeed(heappop(self.items))
        return None


class FilterStore(Store):
    """
    过滤式对象队列。每个 get 请求可携带独立过滤函数，队列中第一个满足条件的对象会被返回。
    """

    if TYPE_CHECKING:

        def get(
            self, filter: Callable[[Any], bool] = lambda item: True
        ) -> FilterStoreGet:
            """
            执行 ``FilterStore.get`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return FilterStoreGet(self, filter)

    else:
        get = BoundClass(FilterStoreGet)

    def _do_get(  # type: ignore[override]
        self, event: FilterStoreGet
    ) -> Optional[bool]:
        for item in self.items:
            if event.filter(item):
                self.items.remove(item)
                event.succeed(item)
                break
        return True
