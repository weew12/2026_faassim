"""
SimPy 离散事件仿真环境核心。

本文件实现 faas-sim 运行时最关键的事件队列和仿真时钟推进机制。``Environment``
维护按时间、优先级和事件序号排序的堆队列；每次 ``step`` 取出下一个事件并触发回调；
``run`` 则持续推进事件，直到指定时间、指定事件或事件队列耗尽。

在 faas-sim 中，函数副本部署、镜像拉取、启动、setup、请求执行、资源监控和自动
伸缩器都以 SimPy 进程或事件的形式挂载到该环境中，因此这里是整个仿真系统的时间
轴和调度循环。
"""

from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from types import MethodType
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from simpy.events import (
    NORMAL,
    URGENT,
    AllOf,
    AnyOf,
    Event,
    EventPriority,
    Process,
    ProcessGenerator,
    Timeout,
)

Infinity: float = float('inf')  # 无穷大别名，用于表示事件队列已经没有下一个事件。

T = TypeVar('T')


class BoundClass(Generic[T]):
    """
    描述符工具类，用于把事件类绑定成环境或资源对象上的方法。faas-sim 调用 ``env.timeout``、``env.process`` 时，实际就是通过该机制快速构造 Timeout 与 Process 事件。
    """

    def __init__(self, cls: Type[T]):
        # 字段：被包装的事件类或请求类，描述符绑定后会表现为实例方法。
        self.cls = cls

    def __get__(
        self,
        instance: Optional[BoundClass],
        owner: Optional[Type[BoundClass]] = None,
    ) -> Union[Type[T], MethodType]:
        if instance is None:
            return self.cls
        return MethodType(self.cls, instance)

    @staticmethod
    def bind_early(instance: object) -> None:
        """
        提前把实例类中的 BoundClass 属性绑定到实例，减少仿真循环中的描述符解析开销。
        """
        for name, obj in instance.__class__.__dict__.items():
            if type(obj) is BoundClass:
                bound_class = getattr(instance, name)
                setattr(instance, name, bound_class)


class EmptySchedule(Exception):
    """
    事件队列为空异常。当 Environment 继续 step 但没有任何待处理事件时抛出，run 可据此判断仿真自然结束。
    """


class StopSimulation(Exception):
    """
    仿真停止信号异常。run 等待 until 事件时，会把该事件的完成结果转换为该异常，从而跳出事件循环并返回结果。
    """

    @classmethod
    def callback(cls, event: Event) -> None:
        """
        作为 until 事件的回调使用：事件成功时终止仿真并携带结果，事件失败时传播原始异常。
        """
        if event.ok:
            raise cls(event.value)
        else:
            raise event._value


SimTime = Union[int, float]


class Environment:
    """
    离散事件仿真环境。该类维护当前仿真时间、事件优先队列、事件序号生成器和当前活动进程，是 faas-sim 所有部署、调用、监控、调度和网络传输流程的统一时间轴。
    """

    def __init__(self, initial_time: SimTime = 0):
        # 字段：当前仿真时间，所有事件处理都会把该值推进到事件发生时间。
        self._now = initial_time
        self._queue: List[
            Tuple[SimTime, EventPriority, int, Event]
        ] = []  # 当前已经调度但尚未处理的事件堆队列。
        # 字段：事件编号计数器，用于在同一时间和优先级下保持确定性处理顺序。
        self._eid = count()  # 事件编号计数器，用于保证同时间事件处理顺序稳定。
        # 字段：当前正在执行的进程，资源请求会用它记录请求发起者。
        self._active_proc: Optional[Process] = None

        # 提前绑定 BoundClass 事件构造器，降低仿真循环开销。
        BoundClass.bind_early(self)

    @property
    def now(self) -> SimTime:
        """
        返回当前仿真时间。faas-sim 的部署时间、请求到达时间和指标时间戳均来自该属性。
        """
        return self._now

    @property
    def active_process(self) -> Optional[Process]:
        """
        返回当前正在恢复执行的 Process；资源请求会用它记录请求由哪个进程发起。
        """
        return self._active_proc

    if TYPE_CHECKING:
        # 该分支仅在静态类型检查时生效，用于给动态绑定方法提供类型签名。
        # 这些签名描述 BoundClass 动态生成方法的实际调用形态。

        def process(self, generator: ProcessGenerator) -> Process:
            """
            把生成器包装成 Process，并安排其作为仿真后台进程或业务进程运行。
            """
            return Process(self, generator)

        def timeout(self, delay: SimTime = 0, value: Optional[Any] = None) -> Timeout:
            """
            创建延时事件，用于表达冷启动、函数执行、监控周期等仿真耗时。
            """
            return Timeout(self, delay, value)

        def event(self) -> Event:
            """
            创建一个手动触发事件，供不同进程之间同步等待。
            """
            return Event(self)

        def all_of(self, events: Iterable[Event]) -> AllOf:
            """
            创建等待所有输入事件完成的组合事件。
            """
            return AllOf(self, events)

        def any_of(self, events: Iterable[Event]) -> AnyOf:
            """
            创建等待任一输入事件完成的组合事件。
            """
            return AnyOf(self, events)

    else:
        process = BoundClass(Process)
        timeout = BoundClass(Timeout)
        event = BoundClass(Event)
        all_of = BoundClass(AllOf)
        any_of = BoundClass(AnyOf)

    def schedule(
        self,
        event: Event,
        priority: EventPriority = NORMAL,
        delay: SimTime = 0,
    ) -> None:
        """
        把事件按目标时间、优先级和递增编号放入堆队列，等待后续 step 处理。
        """
        heappush(self._queue, (self._now + delay, priority, next(self._eid), event))

    def peek(self) -> SimTime:
        """
        查看下一个待处理事件的仿真时间；若队列为空则返回无穷大。
        """
        try:
            return self._queue[0][0]
        except IndexError:
            return Infinity

    def step(self) -> None:
        """
        推进一个离散事件：弹出队首事件、更新当前时间、执行回调，并处理失败事件或停止信号。
        """
        try:
            self._now, _, _, event = heappop(self._queue)
        except IndexError:
            raise EmptySchedule from None

        # 处理事件回调，并立即清空回调列表以避免处理期间被重复修改。
        callbacks, event.callbacks = event.callbacks, None  # type: ignore
        try:
            for callback in callbacks:
                callback(event)
        except StopSimulation:
            # 停止仿真前把尚未执行的回调重新挂回事件，便于后续恢复运行。
            event.callbacks = callbacks[callbacks.index(callback) + 1 :]
            self.schedule(event, EventPriority(-1))
            raise

        if not event._ok and not hasattr(event, '_defused'):
            # 事件失败且异常未被消解时，环境需要把异常抛给调用方。
            # 复制异常对象，保留原始异常作为 cause，避免回溯被复用污染。
            exc = type(event._value)(*event._value.args)
            exc.__cause__ = event._value
            raise exc

    def run(self, until: Optional[Union[SimTime, Event]] = None) -> Optional[Any]:
        """
        持续调用 step 推进仿真，直到队列耗尽、到达指定时间或指定事件完成。
        """
        if until is not None:
            if not isinstance(until, Event):
                at: SimTime = until if isinstance(until, int) else float(until)

                if at <= self.now:
                    raise ValueError(
                        f'until ({at}) must be greater than the current simulation time'
                    )

                until = Event(self)
                until._ok = True
                until._value = None
                self.schedule(until, URGENT, at - self.now)

            elif until.callbacks is None:
                return until.value

            until.callbacks.append(StopSimulation.callback)

        try:
            while True:
                self.step()
        except StopSimulation as exc:
            return exc.args[0]  # 返回 until 事件的完成值。
        except EmptySchedule:
            if until is not None:
                assert not until.triggered
                raise RuntimeError(
                    f'No scheduled events left but "until" event was not '
                    f'triggered: {until}'
                ) from None
        return None
