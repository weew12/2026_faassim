"""
SimPy 有限并发槽位资源模型。

本文件实现类似互斥锁/信号量的资源对象。``Resource`` 限制同一时刻可持有资源的
进程数量；``PriorityResource`` 在等待队列中按优先级排序；``PreemptiveResource``
允许高优先级请求抢占低优先级用户并向被抢占进程发送中断。

faas-sim 衔接：
- 函数副本 worker 数（CPU/GPU worker）：用 ``Resource`` 或 ``PriorityResource``；
- 设备独占资源（独占磁盘、独占网卡）：用 ``Resource(capacity=1)`` 模拟互斥锁；
- 抢占式副本伸缩：当紧急任务到达时用 ``PreemptiveResource`` 抢断低优先级副本，
  被抢占进程通过 ``except Interrupt as i: i.cause`` 拿到 ``Preempted`` 对象。
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
    抢占原因对象。

    ``PreemptiveResource`` 抢占低优先级用户时，会把抢占者、被抢占者占用起始时间
    和资源对象封装到该对象中，再作为 ``Interrupt(cause=Preempted(...))`` 的 cause
    投递给被抢占进程。被抢占的进程可在 ``except Interrupt as i:`` 处通过
    ``i.cause`` 拿到这个对象自行处理（清理资源 / 退出 / 重试）。
    """

    def __init__(
        self,
        by: Optional[Process],
        usage_since: Optional[SimTime],
        resource: Resource,
    ):
        # 字段：导致当前进程被抢占的抢占者进程。可能是 None（理论上不会出现）。
        self.by = by
        # 字段：被抢占进程开始占用资源的仿真时间。可用于统计"已运行时长"。
        self.usage_since = usage_since
        # 字段：该请求操作所属的资源对象。被抢占进程可用它重新发起 request。
        self.resource = resource


class Request(base.Put):
    """
    Resource 的使用申请事件。

    成功后表示当前进程占用了一个资源槽，通常配合 ``with`` 使用以便自动释放。
    资源占用起始时间记录在 ``usage_since`` 上，便于业务层做"占用时长"统计。
    """

    # 类型标注：让 IDE 知道 Request.resource 一定是 Resource（而不是泛型）。
    resource: Resource

    # 资源申请成功并开始占用资源的仿真时间。
    # 在 Request 构造时为 None；Resource._do_put 满足请求时写入 env.now。
    usage_since: Optional[SimTime] = None

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        # 父类 base.Put.__exit__ 会自动 cancel 未触发的请求。
        super().__exit__(exc_type, exc_value, traceback)
        # 生成器清理阶段不自动释放资源，避免形成不可回收的循环引用。
        # GeneratorExit 是生成器被 close() 或被 GC 时抛的特殊异常；这阶段往往
        # 业务状态已经不清不楚，自动 release 可能让"本应保留的槽"被错误释放。
        if exc_type is not GeneratorExit:
            self.resource.release(self)
        return None


class Release(base.Get):
    """
    Resource 的释放事件。

    它释放某个已经成功的 Request，使等待队列中的后续请求有机会获得资源槽。
    业务层通常不直接构造：要么 ``with resource.request() as req:`` 退出时自动
    触发，要么显式 ``resource.release(req)``。
    """

    def __init__(self, resource: Resource, request: Request):
        # 字段：Release 要释放的资源申请事件。Resource._do_get 据此从 users 移除。
        self.request = request
        # 父类 Get.__init__ 会完成：构造 Event、挂 get_queue、注册 _trigger_put 回调、
        # 调用 _trigger_get 立即尝试满足。
        super().__init__(resource)


class PriorityRequest(Request):
    """
    带优先级的资源申请事件。

    它记录优先级、申请时间和是否允许抢占，并生成排序 key 供优先级队列使用。
    key 是 ``(priority, time, not preempt)`` 三元组：
    - ``priority`` 越小越优先；
    - 同优先级按 ``time`` 升序（FIFO，避免饥饿）；
    - 同优先级同时刻按 ``not preempt`` 升序——``preempt=True`` 的排前面，让
      抢占意图更强的请求先得到资源。
    """

    def __init__(self, resource: Resource, priority: int = 0, preempt: bool = True):
        # 字段：资源申请优先级，数值越小优先级越高。
        self.priority = priority

        # 字段：是否允许该请求抢占当前资源用户。
        # ``preempt=False`` 表示"我只排队等空槽，不要抢别人的"——适合必须跑完
        # 的关键任务不希望被中断。
        self.preempt = preempt

        # 字段：资源申请发起时的仿真时间，用于同优先级请求排序。
        self.time = resource._env.now

        # 字段：优先级队列排序键，综合优先级、申请时间和抢占标志。
        # SortedQueue.append 会用 ``e.key`` 排序整个队列。
        self.key = (self.priority, self.time, not self.preempt)

        # 调用 Request.__init__ → Put.__init__ 完成事件注册流程。
        super().__init__(resource)


class SortedQueue(list):
    """
    按请求 ``key`` 自动排序的队列。

    ``PriorityResource`` 与 ``PreemptiveResource`` 用它维护等待请求。每次 append
    后立即对整列表按 ``key`` 排序，保证队首始终是当前"最值得优先满足"的请求。
    """

    def __init__(self, maxlen: Optional[int] = None):
        super().__init__()
        # 字段：排序队列最大长度限制，None 表示不限制。
        # 与 ``queue.Queue`` 不同，SortedQueue 不做阻塞入队；满了直接抛错。
        self.maxlen = maxlen

    def append(self, item: Any) -> None:
        """
        把新请求加入队列并按 key 排序，队列满时抛出异常。

        注意：每次 append 都触发一次 ``list.sort``，因此 SortedQueue 的入队是
        O(n log n)；如果业务量极大可以考虑换成 heap。
        """
        if self.maxlen is not None and len(self) >= self.maxlen:
            raise RuntimeError('Cannot append event. Queue is full.')

        super().append(item)
        # 按 key 排序：key 越小越靠前。``super().sort`` 走 list 自带的 Timsort。
        super().sort(key=lambda e: e.key)


class Resource(base.BaseResource):
    """
    有限并发槽位资源。

    它维护当前 ``users`` 与等待 ``queue``，可用于模拟 worker 池、连接池、函数
    实例并发槽等资源。``capacity=1`` 时退化为互斥锁；``capacity>1`` 时类似信号量。
    """

    def __init__(self, env: Environment, capacity: int = 1):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')

        super().__init__(env, capacity)

        # 字段：当前已经获得资源槽的请求列表。
        self.users: List[Request] = []
        # 字段：等待资源槽的请求队列，是 put_queue 的公开别名。
        # 业务层可以直接读 ``resource.queue`` 看等待长度，便于监控 / 调度。
        self.queue = self.put_queue

    @property
    def count(self) -> int:
        """
        返回当前正在使用资源槽的请求数量。
        """
        return len(self.users)

    if TYPE_CHECKING:
        # 仅静态类型检查分支，给 IDE / mypy 提供 request / release 的签名。

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
        # 运行时：BoundClass 动态绑定无参 request / 带 Request 的 release。
        request = BoundClass(Request)
        release = BoundClass(Release)

    def _do_put(self, event: Request) -> None:
        # 槽位未满时占用并 succeed，写入 usage_since 便于统计。
        if len(self.users) < self.capacity:
            self.users.append(event)
            event.usage_since = self._env.now
            event.succeed()

    def _do_get(self, event: Release) -> None:
        # 从 users 移除对应 request。找不到（可能重复 release）就忽略。
        try:
            self.users.remove(event.request)  # type: ignore
        except ValueError:
            pass
        event.succeed()


class PriorityResource(Resource):
    """
    优先级资源。

    它继承 ``Resource``，但等待队列按 ``PriorityRequest.key`` 排序，使高优先级
    进程优先获得资源。本类**不**实现抢占语义——抢占由子类
    ``PreemptiveResource`` 提供。
    """

    # 把 put_queue 替换为 SortedQueue，让等待请求按 PriorityRequest.key 排序。
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
    抢占式优先级资源。

    高优先级请求可抢占当前低优先级用户，并向被抢占进程发送 ``Interrupt``。
    抢占后原槽位空出，本次新请求沿用 ``super()._do_put`` 走正常占用流程。
    """

    # 类型标注收窄：users 里全是 PriorityRequest，便于抢占时取 preempt.key。
    users: List[PriorityRequest]  # type: ignore

    def _do_put(  # type: ignore[override]
        self, event: PriorityRequest
    ) -> None:
        # 仅当槽位已满**且**新请求允许抢占时，才尝试抢占。
        if len(self.users) >= self.capacity and event.preempt:
            # 从当前 users 中找 key 最大的（即"最不优先"的用户）。key 是
            # (priority, time, not preempt)，数值越大优先级越低。
            preempt = max(self.users, key=lambda e: e.key)
            if preempt.key > event.key:
                # 严格大于：新请求确实更优先。把 preempt 从 users 移除，
                # 并向其进程注入 Interrupt(cause=Preempted(...))。
                self.users.remove(preempt)
                preempt.proc.interrupt(  # type: ignore
                    Preempted(
                        by=event.proc,
                        usage_since=preempt.usage_since,
                        resource=self,
                    )
                )

        # 不论是否真的抢到用户，都调用 super()._do_put：
        #   - 抢出空位：本步会成功占用；
        #   - 没抢到且原本就没空位：本步不会触发，事件留在 SortedQueue 等待。
        return super()._do_put(event)