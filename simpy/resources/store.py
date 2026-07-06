"""
SimPy 离散对象存储与队列模型。

本文件实现面向对象项的队列资源。``Store`` 按 FIFO 保存对象；``PriorityStore``
使用堆按优先级弹出对象；``FilterStore`` 允许 ``get`` 请求指定过滤条件，只取满足
条件的对象。

faas-sim 中适合建模：
- 请求队列（用户请求对象按到达顺序排队）；
- 消息队列（节点间传输的消息）；
- 任务缓冲区（等待 worker 取走执行的任务）；
- 负载均衡器内部按路由 / 类型分发的等待队列。
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
        # 父类 Put.__init__ 会完成：构造 Event、挂 put_queue、注册 _trigger_get 回调、
        # 调用 _trigger_put 立即尝试满足。Store._do_put 看到 item 后判断剩余容量。
        super().__init__(store)


class StoreGet(base.Get):
    """
    Store 的出队事件。它从离散对象队列中取出一个对象项。

    不携带额外字段——出队对象的具体取值在 Store._do_get 满足时通过
    ``event.succeed(item)`` 写入。
    """


class FilterStoreGet(StoreGet):
    """
    带过滤条件的出队事件。它只在队列中存在满足 ``filter`` 函数的对象时成功。
    """

    def __init__(
        self,
        resource: FilterStore,
        filter: Callable[[Any], bool] = lambda item: True,
    ):
        # 字段：FilterStoreGet 用于选择对象的过滤函数。
        # 默认 ``lambda item: True`` 表示接受所有对象，等价于 ``StoreGet``。
        self.filter = filter
        # 父类 StoreGet.__init__ 不带参数，再上一级 Get.__init__ 完成事件注册。
        super().__init__(resource)


class Store(base.BaseResource):
    """
    FIFO 离散对象队列。

    ``put`` 添加对象到队尾，``get`` 取出队首对象，容量满或队列空时请求会等待。
    ``items`` 字段保存当前队列内容，按到达顺序排列。

    faas-sim 衔接：副本请求队列、未派发的任务缓冲、节点间消息队列等。
    """

    def __init__(self, env: Environment, capacity: Union[float, int] = float('inf')):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')

        super().__init__(env, capacity)

        # 字段：Store 当前保存的对象列表或堆。
        # ``list`` 在 Store / FilterStore 中按 FIFO 使用，在 PriorityStore 中
        # 通过 heappush / heappop 当作堆使用——同一种数据结构承担两种角色。
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
        # 容量未满时把对象追加到 items 末尾，succeed 之。
        if len(self.items) < self._capacity:
            self.items.append(event.item)
            event.succeed()
        # 返回 None：满则停止本次循环遍历；不满则 _do_put 满足后也没有"继续往下
        # 尝试能让其他 put 也满足"的语义，所以两种情况都返回 None。
        return None

    def _do_get(self, event: StoreGet) -> Optional[bool]:
        # 队列非空时 pop(0) 取出最早入队的对象（FIFO）。
        if self.items:
            event.succeed(self.items.pop(0))
        # 空则返回 None 让请求留在 get_queue 等待。
        return None


class PriorityItem(NamedTuple):
    """
    优先级对象包装器。

    它把 ``priority`` 与 ``item`` 绑定，并只基于 ``priority`` 比较大小，便于
    ``PriorityStore`` 使用堆排序。``NamedTuple`` 让业务层可以 ``pi.priority`` /
    ``pi.item`` 直接解包，调试和日志都很友好。
    """

    # 注意：字段顺序是 (priority, item) 而非 (item, priority)——
    # 业务层构造时应写成 ``PriorityItem(priority=2, item=req)``。
    priority: Any

    item: Any

    def __lt__(  # type: ignore[override]
        self, other: PriorityItem
    ) -> bool:
        # 只比较 priority，item 不参与排序；这样堆里多个 PriorityItem 优先级相同
        # 时的次序由 Python heapq 的稳定行为决定（通常是插入顺序）。
        return self.priority < other.priority


class PriorityStore(Store):
    """
    优先级对象队列。

    队列中的对象按堆结构排序，``get`` 每次返回优先级最小的对象。调用方需要
    把"优先级 + 业务对象"用 ``PriorityItem`` 包装后再 ``put``——堆比较是基于
    PriorityItem 自身的 ``__lt__`` 实现的。
    """

    def _do_put(self, event: StorePut) -> Optional[bool]:
        # 与 Store._do_put 几乎一致，仅追加方式改为 heappush。
        # 注意：put_queue 的 put_event.item 必须是 PriorityItem（或可比较的对象），
        # 否则 heappush 会因为比较规则不一致而乱序。
        if len(self.items) < self._capacity:
            heappush(self.items, event.item)
            event.succeed()
        return None

    def _do_get(self, event: StoreGet) -> Optional[bool]:
        # 弹出堆顶（即优先级最小的对象）。
        if self.items:
            event.succeed(heappop(self.items))
        return None


class FilterStore(Store):
    """
    过滤式对象队列。

    每个 ``get`` 请求可携带独立过滤函数，队列中第一个满足条件的对象会被返回。
    适合"按类型 / 路由 / 标签"分发的场景，例如负载均衡器根据请求类型选择 worker。
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
        # 运行时：get 的覆盖版——带可选 filter 参数。
        get = BoundClass(FilterStoreGet)

    def _do_get(  # type: ignore[override]
        self, event: FilterStoreGet
    ) -> Optional[bool]:
        # 顺序遍历 items，找到第一个满足 filter 的对象后移除并返回。
        # 这里遍历而不是建索引，是因为每次 get 的 filter 可能都不一样，没法预建索引。
        for item in self.items:
            if event.filter(item):
                self.items.remove(item)
                event.succeed(item)
                break
        # 总是返回 True：一次过滤取出后其他 get 可能仍可满足（不同 filter 对应
        # 不同对象），让基类继续遍历剩余 get 请求；即便没有更多 get 可满足，
        # 遍历空循环也只是 no-op，不会出错。
        return True