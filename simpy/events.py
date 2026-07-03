"""
SimPy 事件与进程模型。

本文件定义离散事件仿真的基本执行单元。``Event`` 表示某个未来会完成的状态；
``Timeout`` 表示经过一段仿真时间后自动完成；``Process`` 包装 Python 生成器，使
业务代码可以通过 ``yield event`` 挂起并在事件完成后恢复；``Condition``、``AllOf``
和 ``AnyOf`` 则用于等待多个事件之间的组合关系。

faas-sim 的函数生命周期、请求执行、后台监控、调度器 worker 和网络传输都依靠这些
事件实现非阻塞推进。
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    NewType,
    Optional,
    Tuple,
    TypeVar,
)

from simpy.exceptions import Interrupt

if TYPE_CHECKING:
    from types import FrameType

    from simpy.core import Environment, SimTime

PENDING: object = object()
# 字段说明：事件尚未产生结果时使用的唯一哨兵对象。

EventPriority = NewType('EventPriority', int)

URGENT: EventPriority = EventPriority(0)
# 字段说明：紧急事件优先级，主要用于中断和进程初始化。
NORMAL: EventPriority = EventPriority(1)
# 字段说明：普通事件优先级，大多数业务事件使用该值。


class Event:
    """
    SimPy 事件基类。事件可以处于未触发、已触发待处理、已处理三种状态；进程通过 yield 等待事件，事件完成后由环境调度回调恢复等待者。
    """

    _ok: bool
    _defused: bool
    _value: Any = PENDING

    def __init__(self, env: Environment):
        # 字段：事件所属的仿真环境，决定事件进入哪个事件队列。
        self.env = env
        # 字段：事件处理时要调用的回调列表，进程恢复和条件检查都挂在这里。
        self.callbacks: EventCallbacks = []

    def __repr__(self) -> str:
        """
        返回带对象地址的事件描述，便于调试事件队列。
        """
        return f'<{self._desc()} object at {id(self):#x}>'

    def _desc(self) -> str:
        """
        返回事件的简短描述文本，子类可重写以展示延迟、进程名等信息。
        """
        return f'{self.__class__.__name__}()'

    @property
    def triggered(self) -> bool:
        """
        判断事件是否已经被触发并进入待处理状态。
        """
        return self._value is not PENDING

    @property
    def processed(self) -> bool:
        """
        判断事件是否已经被环境处理完毕；处理后 callbacks 会被置空。
        """
        return self.callbacks is None

    @property
    def ok(self) -> bool:
        """
        返回事件是否成功完成；只能在事件触发后读取。
        """
        return self._ok

    @property
    def defused(self) -> bool:
        """
        判断失败事件的异常是否已被回调消解，已消解的失败不会再次导致环境崩溃。
        """
        return hasattr(self, '_defused')

    @defused.setter
    def defused(self, value: bool) -> None:
        # 字段：失败事件是否已被消解，避免异常在环境层再次抛出。
        self._defused = True

    @property
    def value(self) -> Optional[Any]:
        """
        读取事件完成值；事件尚未触发时访问会报错。
        """
        if self._value is PENDING:
            raise AttributeError(f'Value of {self} is not yet available')
        return self._value

    def trigger(self, event: Event) -> None:
        """
        用另一个事件的成功/失败状态和结果触发当前事件，常用于事件链式传播。
        """
        # 字段：事件是否成功完成，失败事件会携带异常并在未消解时传播。
        self._ok = event._ok
        # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
        self._value = event._value
        self.env.schedule(self)

    def succeed(self, value: Optional[Any] = None) -> Event:
        """
        把事件标记为成功、写入结果值并安排到环境队列中处理。
        """
        if self._value is not PENDING:
            raise RuntimeError(f'{self} has already been triggered')

        self._ok = True
        self._value = value
        self.env.schedule(self)
        return self

    def fail(self, exception: Exception) -> Event:
        """
        把事件标记为失败、写入异常对象并安排到环境队列中处理。
        """
        if self._value is not PENDING:
            raise RuntimeError(f'{self} has already been triggered')
        if not isinstance(exception, BaseException):
            raise TypeError(f'{exception} is not an exception.')
        self._ok = False
        self._value = exception
        self.env.schedule(self)
        return self

    def __and__(self, other: Event) -> Condition:
        """
        构造需要两个事件都完成的 AllOf 条件。
        """
        return Condition(self.env, Condition.all_events, [self, other])

    def __or__(self, other: Event) -> Condition:
        """
        构造两个事件任意一个完成即可触发的 AnyOf 条件。
        """
        return Condition(self.env, Condition.any_events, [self, other])


EventType = TypeVar('EventType', bound=Event)
EventCallback = Callable[[EventType], None]
EventCallbacks = List[EventCallback]


class Timeout(Event):
    """
    延时事件。创建时立即按 delay 安排到事件队列，到达指定仿真时间后成功完成；faas-sim 用它表示镜像拉取、冷启动、函数执行和监控周期等耗时。
    """

    def __init__(
        self,
        env: Environment,
        delay: SimTime,
        value: Optional[Any] = None,
    ):
        if delay < 0:
            raise ValueError(f'Negative delay {delay}')
        # 为减少事件创建开销，这里内联 Event.__init__ 的关键初始化逻辑。
        self.env = env
        self.callbacks: EventCallbacks = []
        self._value = value
        # 字段：Timeout 等待的仿真时长。
        self._delay = delay
        self._ok = True
        env.schedule(self, NORMAL, delay)

    def _desc(self) -> str:
        """
        返回包含延迟和可选结果值的延时事件描述。
        """
        value_str = '' if self._value is None else f', value={self.value}'
        return f'{self.__class__.__name__}({self._delay}{value_str})'


class Initialize(Event):
    """
    进程初始化事件。Process 创建后先生成该事件，并以紧急优先级调度，使生成器在被中断前先完成启动。
    """

    def __init__(self, env: Environment, process: Process):
        # 为减少事件创建开销，这里内联 Event.__init__ 的关键初始化逻辑。
        self.env = env
        self.callbacks: EventCallbacks = [process._resume]
        self._value: Any = None

        # 进程初始化必须使用紧急优先级，保证生成器启动早于外部中断。
        self._ok = True
        env.schedule(self, URGENT)


class Interruption(Event):
    """
    进程中断事件。该事件把 Interrupt 异常投递给目标 Process，用于抢占式资源或外部取消场景。
    """

    def __init__(self, process: Process, cause: Optional[Any]):
        # 为减少事件创建开销，这里内联 Event.__init__ 的关键初始化逻辑。
        self.env = process.env
        self.callbacks: EventCallbacks = [self._interrupt]
        self._value = Interrupt(cause)
        self._ok = False
        self._defused = True

        if process._value is not PENDING:
            raise RuntimeError(f'{process} has terminated and cannot be interrupted.')

        if process is self.env.active_process:
            raise RuntimeError('A process is not allowed to interrupt itself.')

        # 字段：需要被中断或恢复的目标进程。
        self.process = process
        self.env.schedule(self, URGENT)

    def _interrupt(self, event: Event) -> None:
        # 目标进程已经结束时忽略后续中断，避免并发中断重复处理。
        if self.process._value is not PENDING:
            return

        # 进程被中断时通常正等待某个目标事件，需要先移除原恢复回调。
        self.process._target.callbacks.remove(self.process._resume)

        self.process._resume(self)


ProcessGenerator = Generator[Event, Any, Any]


class Process(Event):
    """
    生成器进程包装器。它本身也是事件，负责驱动用户生成器不断 yield 下一个事件，并在目标事件完成后恢复生成器执行。
    """

    def __init__(self, env: Environment, generator: ProcessGenerator):
        if not hasattr(generator, 'throw'):
            # 实现说明：不同 Python 实现的生成器类型不同，因此这里采用能力检查。
            raise ValueError(f'{generator} is not a generator.')

        # 为减少事件创建开销，这里内联 Event.__init__ 的关键初始化逻辑。
        self.env = env
        self.callbacks: EventCallbacks = []

        # 字段：被 Process 包装的 Python 生成器，业务流程通过 yield 事件暂停。
        self._generator = generator

        # 安排进程生成器首次执行。
        # 字段：当前进程正在等待的目标事件，目标完成后进程会继续恢复。
        self._target: Event = Initialize(env, self)

    def _desc(self) -> str:
        """
        返回包含生成器函数名的进程描述。
        """
        return f'{self.__class__.__name__}({self.name})'

    @property
    def target(self) -> Event:
        """
        返回当前进程正在等待的目标事件。
        """
        return self._target

    @property
    def name(self) -> str:
        """
        返回启动该进程的生成器函数名。
        """
        return self._generator.__name__  # type: ignore

    @property
    def is_alive(self) -> bool:
        """
        判断生成器是否仍未结束。
        """
        return self._value is PENDING

    def interrupt(self, cause: Optional[Any] = None) -> None:
        """
        向当前进程发送中断请求，底层会创建 Interruption 事件。
        """
        Interruption(self, cause)

    def _resume(self, event: Event) -> None:
        """
        恢复进程生成器执行：向生成器发送事件值或异常，接收下一个等待事件，并注册恢复回调。
        """
        # 标记当前正在恢复的活动进程。
        self.env._active_proc = self

        while True:
            # 从生成器中取得下一步要等待的事件。
            try:
                if event._ok:
                    event = self._generator.send(event._value)
                else:
                    # 失败事件会作为异常抛入生成器，由业务进程自行处理或继续失败。
                    event._defused = True

                    # 为当前进程复制异常对象，避免多个进程共享同一回溯对象。
                    exc = type(event._value)(*event._value.args)
                    exc.__cause__ = event._value
                    event = self._generator.throw(exc)
            except StopIteration as e:
                # 进程生成器正常结束，Process 事件随之成功。
                event = None  # type: ignore
                # 字段：事件是否成功完成，失败事件会携带异常并在未消解时传播。
                self._ok = True
                # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
                self._value = e.args[0] if len(e.args) else None
                self.env.schedule(self)
                break
            except BaseException as e:
                # 进程生成器抛出异常，Process 事件随之失败。
                event = None  # type: ignore
                self._ok = False
                # 去掉当前恢复函数的栈帧，使错误定位更贴近业务生成器。
                e.__traceback__ = e.__traceback__.tb_next  # type: ignore
                self._value = e
                self.env.schedule(self)
                break

            # 生成器返回了新的等待事件。
            try:
                # 先按事件对象处理，若不是合法事件再构造错误提示。
                if event.callbacks is not None:
                    # 目标事件尚未处理，注册恢复回调等待其完成。
                    event.callbacks.append(self._resume)
                    break
            except AttributeError:
                # 生成器 yield 的不是合法事件，生成带源码位置的错误提示。
                if hasattr(event, 'callbacks'):
                    raise

                msg = f'Invalid yield value "{event}"'
                descr = _describe_frame(self._generator.gi_frame)  # type: ignore[attr-defined]
                raise RuntimeError(f'\n{descr}{msg}') from None

        self._target = event
        self.env._active_proc = None


class ConditionValue:
    """
    组合条件事件的结果容器。它保存已经满足条件的原始事件，并提供字典式访问事件值的能力。
    """

    def __init__(self) -> None:
        # 字段：条件结果或队列中保存的事件/对象列表。
        self.events: List[Event] = []

    def __getitem__(self, key: Event) -> Any:
        if key not in self.events:
            raise KeyError(str(key))

        return key._value

    def __contains__(self, key: Event) -> bool:
        return key in self.events

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ConditionValue):
            return self.events == other.events
        elif isinstance(other, dict):
            return self.todict() == other
        else:
            return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f'<ConditionValue {self.todict()}>'

    def __iter__(self) -> Iterator[Event]:
        return self.keys()

    def keys(self) -> Iterator[Event]:
        return (event for event in self.events)

    def values(self) -> Iterator[Any]:
        return (event._value for event in self.events)

    def items(self) -> Iterator[Tuple[Event, Any]]:
        return ((event, event._value) for event in self.events)

    def todict(self) -> Dict[Event, Any]:
        return {event: event._value for event in self.events}


class Condition(Event):
    """
    组合条件事件。它监听一组事件，并用 evaluate 函数判断何时完成；AllOf 和 AnyOf 分别用它实现“全部完成”和“任一完成”。
    """

    def __init__(
        self,
        env: Environment,
        evaluate: Callable[[Tuple[Event, ...], int], bool],
        events: Iterable[Event],
    ):
        super().__init__(env)
        # 字段：组合条件判断函数，用于判断输入事件集合是否满足触发条件。
        self._evaluate = evaluate
        # 字段：组合条件监听的输入事件元组。
        self._events = tuple(events)
        # 字段：组合条件中已经完成并触发检查的事件数量。
        self._count = 0

        if not self._events:
            # 没有输入事件时条件立即成功。
            self.succeed(ConditionValue())
            return

        # 组合条件要求所有输入事件来自同一个仿真环境。
        for event in self._events:
            if self.env != event.env:
                raise ValueError(
                    'It is not allowed to mix events from different environments'
                )

        # 为每个输入事件注册条件检查回调，已处理事件则立即检查。
        for event in self._events:
            if event.callbacks is None:
                self._check(event)
            else:
                event.callbacks.append(self._check)

        # 条件触发后注册结果构造回调。
        assert isinstance(self.callbacks, list)
        self.callbacks.append(self._build_value)

    def _desc(self) -> str:
        """
        返回包含判断函数和输入事件列表的条件描述。
        """
        return f'{self.__class__.__name__}({self._evaluate.__name__}, {self._events})'

    def _populate_value(self, value: ConditionValue) -> None:
        """
        递归收集已完成的输入事件，填充 ConditionValue。
        """

        for event in self._events:
            if isinstance(event, Condition):
                event._populate_value(value)
            elif event.callbacks is None:
                value.events.append(event)

    def _build_value(self, event: Event) -> None:
        """
        条件事件处理时移除检查回调，并在成功时构造条件结果。
        """
        self._remove_check_callbacks()
        if event._ok:
            # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
            self._value = ConditionValue()
            self._populate_value(self._value)

    def _remove_check_callbacks(self) -> None:
        """
        递归移除输入事件上的检查回调，避免条件完成后留下循环引用。
        """
        for event in self._events:
            if event.callbacks and self._check in event.callbacks:
                event.callbacks.remove(self._check)
            if isinstance(event, Condition):
                event._remove_check_callbacks()

    def _check(self, event: Event) -> None:
        """
        输入事件完成时检查组合条件是否满足，满足则触发条件事件。
        """
        if self._value is not PENDING:
            return

        self._count += 1

        if not event._ok:
            # 事件失败且异常未被消解时，环境需要把异常抛给调用方。
            event._defused = True
            self.fail(event._value)
        elif self._evaluate(self._events, self._count):
            # 条件满足后触发自身，结果值稍后由 _build_value 填充。
            self.succeed()

    @staticmethod
    def all_events(events: Tuple[Event, ...], count: int) -> bool:
        """
        判断输入事件是否已经全部完成。
        """
        return len(events) == count

    @staticmethod
    def any_events(events: Tuple[Event, ...], count: int) -> bool:
        """
        判断是否至少已有一个输入事件完成。
        """
        return count > 0 or len(events) == 0


class AllOf(Condition):
    """
    全部完成条件事件。只有输入事件全部成功触发后才成功，任一事件失败时立即失败。
    """

    def __init__(self, env: Environment, events: Iterable[Event]):
        super().__init__(env, Condition.all_events, events)


class AnyOf(Condition):
    """
    任一完成条件事件。输入事件中任意一个成功触发后即成功，失败会向外传播。
    """

    def __init__(self, env: Environment, events: Iterable[Event]):
        super().__init__(env, Condition.any_events, events)


def _describe_frame(frame: FrameType) -> str:
    """
    生成包含文件名、行号和代码行的错误定位文本，用于提示非法 yield 的位置。
    """
    filename, name = frame.f_code.co_filename, frame.f_code.co_name
    lineno = frame.f_lineno

    with open(filename) as f:
        for no, line in enumerate(f):
            if no + 1 == lineno:
                return (
                    f'  File "{filename}", line {lineno}, in {name}\n'
                    f'    {line.strip()}\n'
                )
        return f'  File "{filename}", line {lineno}, in {name}\n'
