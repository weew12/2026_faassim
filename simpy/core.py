"""
SimPy 离散事件仿真环境核心。

本文件实现 faas-sim 运行时最关键的事件队列和仿真时钟推进机制。``Environment``
维护按时间、优先级和事件序号排序的堆队列；每次 ``step`` 取出下一个事件并触发回调；
``run`` 则持续推进事件，直到指定时间、指定事件或事件队列耗尽。

faas-sim 中"函数副本部署、镜像拉取、启动 setup、请求执行、资源监控和自动
伸缩器"都以 SimPy 进程或事件的形式挂载到该环境中，因此这里是整个仿真系统的时间
轴和调度循环。

具体衔接点：
- faas-sim 的 ``sim.core.Environment`` 直接继承本类，仅在其上叠加 FaaS 业务字段；
- 副本生命周期通过 ``env.process(lifecycle(env, ...))`` 启动；
- 冷启动 / 执行 / 监控周期通过 ``env.timeout(seconds)`` 表达；
- 资源监控与自动伸缩器通常作为独立进程常驻在 ``env`` 上。
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

# 下面的 import 跨模块：core 依赖 events 的事件类与优先级常量，events 又依赖
# exceptions 的 Interrupt。这种依赖方向决定了 core 是"较低层"的实现。
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

# 无穷大别名：用于表示事件队列已经没有下一个事件（见 ``Environment.peek``）。
Infinity: float = float('inf')

T = TypeVar('T')


class BoundClass(Generic[T]):
    """
    描述符工具类，用于把事件类绑定成环境或资源对象上的方法。

    faas-sim 调用 ``env.timeout(...)``、``env.process(...)``、``resource.put(...)``
    时，实际就是通过该机制把事件/请求类"伪装"成实例方法，从而省去显式传入
    ``env=...`` 的样板。

    设计动机：相比 ``functools.partial(cls, env)``，``BoundClass`` 走描述符协议，
    在 ``TYPE_CHECKING`` 分支还能给 IDE / mypy 提示完整的方法签名。
    """

    def __init__(self, cls: Type[T]):
        # 字段：被包装的事件类或请求类，描述符绑定后会表现为实例方法。
        self.cls = cls

    def __get__(
        self,
        instance: Optional[BoundClass],
        owner: Optional[Type[BoundClass]] = None,
    ) -> Union[Type[T], MethodType]:
        # 两种访问形式：
        # - 类上访问（``Environment.process``）→ 返回原始类，让调用方自己 new；
        # - 实例上访问（``env.process``）→ 返回 ``MethodType(cls, instance)``，
        #   调用时自动把 instance 作为第一个参数绑定。
        if instance is None:
            return self.cls
        return MethodType(self.cls, instance)

    @staticmethod
    def bind_early(instance: object) -> None:
        """
        提前把实例类中的 ``BoundClass`` 属性绑定到实例，减少仿真循环中的描述符解析开销。

        实现：遍历类字典，找到所有 ``BoundClass`` 描述符，主动调用 ``getattr``
        触发 ``__get__`` 拿到 ``MethodType``，再用 ``setattr`` 写到实例属性上。
        后续访问该属性时直接走实例字典，跳过描述符协议。
        """
        for name, obj in instance.__class__.__dict__.items():
            if type(obj) is BoundClass:
                # getattr 会触发 BoundClass.__get__，返回绑定了 instance 的 MethodType
                bound_class = getattr(instance, name)
                # 写到实例属性上，后续访问绕过描述符协议
                setattr(instance, name, bound_class)


class EmptySchedule(Exception):
    """
    事件队列为空异常。

    当 ``Environment`` 继续 ``step`` 但没有任何待处理事件时抛出。``run`` 可据此
    判断仿真自然结束；如果 ``run(until=...)`` 给定了一个事件但队列提前耗尽，
    则 ``run`` 会把 ``EmptySchedule`` 转化为 ``RuntimeError`` 抛出。
    """


class StopSimulation(Exception):
    """
    仿真停止信号异常。

    ``run(until=event)`` 时，会把该事件的完成结果转换为 ``StopSimulation(event.value)``，
    从而跳出事件循环并把结果作为 ``run`` 的返回值。
    """

    @classmethod
    def callback(cls, event: Event) -> None:
        """
        作为 ``until`` 事件的回调使用：事件成功时终止仿真并携带结果，事件失败时
        传播原始异常。
        """
        if event.ok:
            # 成功：把 ``event.value`` 装入 StopSimulation.args[0]，run 会把它
            # 作为返回值传给调用方。
            raise cls(event.value)
        else:
            # 失败：把原始异常（可能是 Interrupt 等）直接抛出，让 run 把异常
            # 转发给调用方而不是包装成 StopSimulation。
            raise event._value


# 仿真时间的数值类型：可以是整数秒或浮点秒。仿真内部统一用浮点处理避免类型转换。
SimTime = Union[int, float]


class Environment:
    """
    离散事件仿真环境。

    该类维护当前仿真时间、事件优先队列、事件序号生成器和当前活动进程，是 faas-sim
    所有部署、调用、监控、调度和网络传输流程的统一时间轴。
    """

    def __init__(self, initial_time: SimTime = 0):
        # 字段：当前仿真时间，所有事件处理都会把该值推进到事件发生时间。
        self._now = initial_time
        # 字段：当前已经调度但尚未处理的事件堆队列。
        # 元组含义：(time, priority, eid, event)，
        #   - time   ：事件发生的仿真时间（已包含 delay）
        #   - priority：URGENT=0 或 NORMAL=1，URGENT 优先出队
        #   - eid    ：事件编号，用于同时间同优先级下的确定性 FIFO
        #   - event  ：实际事件对象
        self._queue: List[
            Tuple[SimTime, EventPriority, int, Event]
        ] = []
        # 字段：事件编号计数器。``count()`` 是 itertools 的无限计数器，
        # next() 每次返回一个严格递增的整数；用它保证同时间事件处理顺序稳定。
        self._eid = count()
        # 字段：当前正在执行的进程。资源请求会用它记录请求发起者，便于
        # PreemptiveResource 在抢占时回填 ``Preempted.by`` 等字段。
        self._active_proc: Optional[Process] = None

        # 提前绑定 BoundClass 事件构造器，降低仿真循环开销。bind_early 会把
        # process/timeout/event/all_of/any_of 等描述符一次性解析为 MethodType。
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
        返回当前正在恢复执行的 ``Process``；资源请求会用它记录请求由哪个进程发起。
        """
        return self._active_proc

    if TYPE_CHECKING:
        # 该分支仅在静态类型检查时生效，用于给动态绑定方法提供类型签名。
        # 这些签名描述 ``BoundClass`` 动态生成方法的实际调用形态。

        def process(self, generator: ProcessGenerator) -> Process:
            """
            把生成器包装成 ``Process``，并安排其作为仿真后台进程或业务进程运行。
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
        # 运行时分支：通过 BoundClass 把 5 个常用构造器动态绑定到实例。
        # bind_early 已把它们转为 MethodType，所以这些赋值看起来"覆盖"
        # 了上面的 BoundClass 描述符，访问时直接命中实例字典。
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
        把事件按目标时间、优先级和递增编号放入堆队列，等待后续 ``step`` 处理。

        排序键 ``(time, priority, eid)`` 的语义：
        - 先按 time：仿真时间最早的事件先出队；
        - 同 time 按 priority：URGENT(=0) 优先于 NORMAL(=1)；
        - 再按 eid：同 time 同 priority 下，按事件创建顺序（确定性 FIFO）。
        """
        # heappush 走 ``<`` 元组比较，所以 (time, priority, eid) 越小越先出队；
        # URGENT=0 < NORMAL=1，因此紧急事件总是更靠前。
        heappush(self._queue, (self._now + delay, priority, next(self._eid), event))

    def peek(self) -> SimTime:
        """
        查看下一个待处理事件的仿真时间；若队列为空则返回无穷大 ``Infinity``。

        该方法不弹出事件，只读取堆顶。``RealtimeEnvironment`` 用它计算"还要 sleep
        多久才能追上墙钟"。
        """
        try:
            return self._queue[0][0]
        except IndexError:
            # 队列空时返回 Infinity 而不是抛异常，便于调用方做 ``if evt_time is Infinity``
            # 这种等价比较。
            return Infinity

    def step(self) -> None:
        """
        推进一个离散事件：弹出队首事件、更新当前时间、执行回调，并处理失败事件或停止信号。

        详细步骤：
        1. ``heappop`` 取出队首事件（依据 ``(time, priority, eid)`` 三元组最小者）；
        2. 把 ``_now`` 推进到事件发生时间；
        3. 把 ``event.callbacks`` 暂存到局部变量并立即置 None，防止处理过程中被
           重新修改（递归触发 / 中断回调都可能在执行期间修改 callbacks）；
        4. 依次执行回调。任一回调抛 ``StopSimulation`` 时，把剩余未执行的回调
           重新挂回事件并以优先级 ``-1`` 重新调度，等待后续恢复运行；
        5. 事件失败且异常未被消解（无 ``_defused`` 标记）时，由环境抛出**复制过**
           的异常（避免多个环境共享同一回溯对象）。

        注意：本方法对外只抛 ``EmptySchedule``、``StopSimulation`` 和"未消解的失败
        事件对应的异常"；其余异常会被某个回调自行处理。
        """
        try:
            self._now, _, _, event = heappop(self._queue)
        except IndexError:
            # 队列空：让 run() 决定是"自然结束"还是"until 还没触发"。
            raise EmptySchedule from None

        # 处理事件回调，并立即清空回调列表以避免处理期间被重复修改。
        # 之所以先 swap 再清空：回调里可能（直接或间接）修改 event.callbacks，
        # 这里要在循环开始前就保证拿到的是稳定快照。
        callbacks, event.callbacks = event.callbacks, None  # type: ignore
        try:
            for callback in callbacks:
                callback(event)
        except StopSimulation:
            # 停止仿真前把尚未执行的回调重新挂回事件，便于后续恢复运行。
            # 用 -1 优先级让这条"复活"事件在下一个 step 里立刻被处理。
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
        持续调用 ``step`` 推进仿真，直到队列耗尽、到达指定时间或指定事件完成。

        ``until`` 支持三种形态：
        - ``None``：跑到队列耗尽为止（自然结束）；
        - 数值（int/float）：内部创建一个 ``URGENT`` 事件，在 ``until`` 时刻成功
          触发，通过 ``StopSimulation`` 退出；
        - ``Event``：把 ``StopSimulation.callback`` 挂到该事件，事件完成后立即
          返回其 ``value``。

        返回值：``until`` 事件的 ``value``，或者 ``None``（自然结束 / ``until=None``）。

        异常：
        - ``ValueError``：``until`` 是数值但不严格大于 ``self.now``；
        - ``RuntimeError``：给了 ``until`` 事件但队列提前耗尽（该事件未触发）。
        """
        if until is not None:
            if not isinstance(until, Event):
                # until 是数值：构造一个"在 at 时刻成功"的事件。
                at: SimTime = until if isinstance(until, int) else float(until)

                if at <= self.now:
                    # at 必须严格大于当前时间；<= 时 step 永远拿不到这个事件，
                    # 直接报错比陷入死循环友好。
                    raise ValueError(
                        f'until ({at}) must be greater than the current simulation time'
                    )

                until = Event(self)
                until._ok = True
                until._value = None
                # URGENT 优先级确保即便同时间也有其他事件，这个终止事件先出队。
                self.schedule(until, URGENT, at - self.now)

            elif until.callbacks is None:
                # until 事件已经处理完（之前就触发过），直接返回它的结果。
                return until.value

            # 把 StopSimulation.callback 挂到 until 事件上，事件完成后立即跳出循环。
            until.callbacks.append(StopSimulation.callback)

        try:
            while True:
                self.step()
        except StopSimulation as exc:
            # 正常退出：返回 until 事件的成功值（如果 until 是数值事件则为 None）。
            return exc.args[0]
        except EmptySchedule:
            if until is not None:
                # 给了 until 但队列提前空了——说明 until 事件没有机会触发。
                # 这种情况通常是业务代码有 bug（比如漏注册某个进程）。
                assert not until.triggered
                raise RuntimeError(
                    f'No scheduled events left but "until" event was not '
                    f'triggered: {until}'
                ) from None
        return None