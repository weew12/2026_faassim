"""
SimPy 有限并发槽位资源模型。

本文件实现类似互斥锁/信号量的资源对象。``Resource`` 限制同一时刻可持有资源的进程
数量；``PriorityResource`` 在等待队列中按优先级排序；``PreemptiveResource`` 允许高
优先级请求抢占低优先级用户并向被抢占进程发送中断。

该模型可用于模拟函数实例 worker 数、设备独占资源、连接池或 GPU 等有限并发资源。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Type

from simpy.core import BoundClass, Environment, SimTime
from simpy.resources import base

if TYPE_CHECKING:
    from types import TracebackType

    from simpy.events import Process


class Preempted:
    """
    抢占原因对象。PreemptiveResource 抢占低优先级用户时，会把抢占者、被抢占者占用起始时间和资源对象封装到该对象中。
    """

    def __init__(
        self,
        by: Optional[Process],
        usage_since: Optional[SimTime],
        resource: Resource,
    ):
        # 字段：导致当前进程被抢占的抢占者进程。
        self.by = by
        # 字段：被抢占进程开始占用资源的仿真时间。
        self.usage_since = usage_since
        # 字段：该请求操作所属的资源对象。
        self.resource = resource


class Request(base.Put):
    """
    Resource 的使用申请事件。成功后表示当前进程占用了一个资源槽，通常配合 with 使用以便自动释放。
    """

    resource: Resource

    # 资源申请成功并开始占用资源的仿真时间。
    usage_since: Optional[SimTime] = None

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        super().__exit__(exc_type, exc_value, traceback)
        # 生成器清理阶段不自动释放资源，避免形成不可回收的循环引用。
        if exc_type is not GeneratorExit:
            self.resource.release(self)
        return None


class Release(base.Get):
    """
    Resource 的释放事件。它释放某个已经成功的 Request，使等待队列中的后续请求有机会获得资源槽。
    """

    def __init__(self, resource: Resource, request: Request):
        # 字段：Release 要释放的资源申请事件。
        self.request = request
        super().__init__(resource)


class PriorityRequest(Request):
    """
    带优先级的资源申请事件。它记录优先级、申请时间和是否允许抢占，并生成排序 key 供优先级队列使用。
    """

    def __init__(self, resource: Resource, priority: int = 0, preempt: bool = True):
        # 字段：资源申请优先级，数值越小优先级越高。
        self.priority = priority

        # 字段：是否允许该请求抢占当前资源用户。
        self.preempt = preempt

        # 字段：资源申请发起时的仿真时间，用于同优先级请求排序。
        self.time = resource._env.now

        # 字段：优先级队列排序键，综合优先级、申请时间和抢占标志。
        self.key = (self.priority, self.time, not self.preempt)

        super().__init__(resource)


class SortedQueue(list):
    """
    按请求 key 自动排序的队列。PriorityResource 与 PreemptiveResource 用它维护等待请求。
    """

    def __init__(self, maxlen: Optional[int] = None):
        super().__init__()
        # 字段：排序队列最大长度限制，None 表示不限制。
        self.maxlen = maxlen

    def append(self, item: Any) -> None:
        """
        把新请求加入队列并按 key 排序，队列满时抛出异常。
        """
        if self.maxlen is not None and len(self) >= self.maxlen:
            raise RuntimeError('Cannot append event. Queue is full.')

        super().append(item)
        super().sort(key=lambda e: e.key)


class Resource(base.BaseResource):
    """
    有限并发槽位资源。它维护当前 users 与等待 queue，可用于模拟 worker 池、连接池、函数实例并发槽等资源。
    """

    def __init__(self, env: Environment, capacity: int = 1):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')

        super().__init__(env, capacity)

        # 字段：当前已经获得资源槽的请求列表。
        self.users: List[Request] = []
        # 字段：等待资源槽的请求队列，是 put_queue 的公开别名。
        self.queue = self.put_queue

    @property
    def count(self) -> int:
        """
        返回当前正在使用资源槽的请求数量。
        """
        return len(self.users)

    if TYPE_CHECKING:

        def request(self) -> Request:
            """
            申请一个资源槽。
            """
            return Request(self)

        def release(self, request: Request) -> Release:
            """
            释放一个已经获得的资源槽。
            """
            return Release(self, request)

    else:
        request = BoundClass(Request)
        release = BoundClass(Release)

    def _do_put(self, event: Request) -> None:
        if len(self.users) < self.capacity:
            self.users.append(event)
            event.usage_since = self._env.now
            event.succeed()

    def _do_get(self, event: Release) -> None:
        try:
            self.users.remove(event.request)  # type: ignore
        except ValueError:
            pass
        event.succeed()


class PriorityResource(Resource):
    """
    优先级资源。它继承 Resource，但等待队列按 PriorityRequest.key 排序，使高优先级进程优先获得资源。
    """

    PutQueue = SortedQueue
    # 字段说明：put 请求队列类型，子类可替换为排序队列等实现。

    GetQueue = list
    # 字段说明：get 请求队列类型，子类可替换为排序队列等实现。

    def __init__(self, env: Environment, capacity: int = 1):
        super().__init__(env, capacity)

    if TYPE_CHECKING:

        def request(self, priority: int = 0, preempt: bool = True) -> PriorityRequest:
            """
            执行 ``PriorityResource.request`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return PriorityRequest(self, priority, preempt)

        def release(  # type: ignore[override]
            self, request: PriorityRequest
        ) -> Release:
            """
            执行 ``PriorityResource.release`` 对应的仿真辅助操作，服务于事件调度、资源管理或进程编排流程。
            """
            return Release(self, request)

    else:
        request = BoundClass(PriorityRequest)
        release = BoundClass(Release)


class PreemptiveResource(PriorityResource):
    """
    抢占式优先级资源。高优先级请求可抢占当前低优先级用户，并向被抢占进程发送 Interrupt。
    """

    users: List[PriorityRequest]  # type: ignore

    def _do_put(  # type: ignore[override]
        self, event: PriorityRequest
    ) -> None:
        if len(self.users) >= self.capacity and event.preempt:
            preempt = max(self.users, key=lambda e: e.key)
            if preempt.key > event.key:
                self.users.remove(preempt)
                preempt.proc.interrupt(  # type: ignore
                    Preempted(
                        by=event.proc,
                        usage_since=preempt.usage_since,
                        resource=self,
                    )
                )

        return super()._do_put(event)
