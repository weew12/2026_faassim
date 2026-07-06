"""
SimPy 事件与进程模型。

本文件定义离散事件仿真的基本执行单元。``Event`` 表示某个未来会完成的状态；
``Timeout`` 表示经过一段仿真时间后自动完成；``Process`` 包装 Python 生成器，使
业务代码可以通过 ``yield event`` 挂起并在事件完成后恢复；``Condition``、``AllOf``
和 ``AnyOf`` 则用于等待多个事件之间的组合关系。

faas-sim 的函数生命周期、请求执行、后台监控、调度器 worker 和网络传输都依靠这些
事件实现非阻塞推进。

模块依赖：本文件 import ``simpy.exceptions.Interrupt``，但 events 本身被 core 依赖，
因此 events 在模块依赖图中位于"core 之下的下一层"。
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

# 事件尚未产生结果时使用的唯一哨兵对象。
# 使用 ``object()`` 而非 ``None`` 是为了和"事件触发后 value 真的是 None"区分开。
PENDING: object = object()

# 事件优先级的类型别名。底层就是 int，但用 NewType 让类型检查器区分"普通整数"
# 和"事件优先级"。
EventPriority = NewType('EventPriority', int)

# 紧急事件优先级，主要用于中断和进程初始化（值越小越优先出队）。
URGENT: EventPriority = EventPriority(0)
# 普通事件优先级，大多数业务事件使用该值。
NORMAL: EventPriority = EventPriority(1)


class Event:
    """
    SimPy 事件基类。

    事件可以处于三种状态：
    - 未触发：``self._value is PENDING``，仍在等待某个时机；
    - 已触发 / 待处理：``self._value is not PENDING and self.callbacks is not None``，
      已经调用 ``succeed/fail/trigger``，即将被 ``Environment.step`` 处理；
    - 已处理：``self.callbacks is None``，回调已执行完毕。

    进程通过 ``yield event`` 等待事件，事件完成后由环境调度回调恢复等待者。
    """

    _ok: bool
    _defused: bool
    _value: Any = PENDING

    def __init__(self, env: Environment):
        # 字段：事件所属的仿真环境，决定事件进入哪个事件队列。
        self.env = env
        # 字段：事件处理时要调用的回调列表。事件被 step 处理后该列表会被置 None，
        # 进程恢复、条件检查、资源触发等回调都挂在这里。
        self.callbacks: EventCallbacks = []

    def __repr__(self) -> str:
        """
        返回带对象地址的事件描述，便于调试事件队列。``id(self):#x`` 输出 16 进制
        内存地址，便于在日志里 grep。
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

        实现：``_value is not PENDING`` 表示事件已被 ``succeed`` / ``fail`` /
        ``trigger`` 写过值并 schedule 进环境队列，等待 step 处理。
        """
        return self._value is not PENDING

    @property
    def processed(self) -> bool:
        """
        判断事件是否已经被环境处理完毕；处理后 ``callbacks`` 会被置空。
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
        # 注意 setter 只允许置 True，无法"取消消解"——失败一旦被消解就不可逆。
        self._defused = True

    @property
    def value(self) -> Optional[Any]:
        """
        读取事件完成值；事件尚未触发时访问会报错。

        faas-sim 业务代码通常这样用：
            ev = env.event()
            ...
            ev.succeed(42)
            assert ev.value == 42   # 此时事件已触发，可以安全读 value
        """
        if self._value is PENDING:
            raise AttributeError(f'Value of {self} is not yet available')
        return self._value

    def trigger(self, event: Event) -> None:
        """
        用另一个事件的成功/失败状态和结果触发当前事件，常用于事件链式传播。

        注意：是**值复制**而非引用，所以即便原事件后续被修改，本事件的结果也
        不会跟着变。
        """
        # 字段：事件是否成功完成，失败事件会携带异常并在未消解时传播。
        self._ok = event._ok
        # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
        self._value = event._value
        # 把自己调度到环境队列，等下一轮 step 处理。
        self.env.schedule(self)

    def succeed(self, value: Optional[Any] = None) -> Event:
        """
        把事件标记为成功、写入结果值并安排到环境队列中处理。
        """
        if self._value is not PENDING:
            # 事件已经被 succeed/fail/trigger 处理过，禁止重复触发。
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
        # fail 要求传入真正的异常对象，避免业务层把字符串当异常传进来后丢失 traceback。
        if not isinstance(exception, BaseException):
            raise TypeError(f'{exception} is not an exception.')
        self._ok = False
        self._value = exception
        self.env.schedule(self)
        return self

    def __and__(self, other: Event) -> Condition:
        """
        构造需要两个事件都完成的 ``AllOf`` 条件。等价于 ``Condition(env, all_events, [...])``。
        """
        return Condition(self.env, Condition.all_events, [self, other])

    def __or__(self, other: Event) -> Condition:
        """
        构造两个事件任意一个完成即可触发的 ``AnyOf`` 条件。
        """
        return Condition(self.env, Condition.any_events, [self, other])


# 类型别名：用于事件回调签名。EventCallback 接收事件自身并返回 None。
EventType = TypeVar('EventType', bound=Event)
EventCallback = Callable[[EventType], None]
EventCallbacks = List[EventCallback]


class Timeout(Event):
    """
    延时事件。

    创建时立即按 ``delay`` 安排到事件队列，到达指定仿真时间后成功完成。faas-sim
    用它表示镜像拉取、冷启动、函数执行和监控周期等耗时。
    """

    def __init__(
        self,
        env: Environment,
        delay: SimTime,
        value: Optional[Any] = None,
    ):
        if delay < 0:
            # 负 delay 没有仿真意义；拒绝构造比"静默按 0 处理"更安全。
            raise ValueError(f'Negative delay {delay}')
        # 为减少事件创建开销，这里内联 Event.__init__ 的关键初始化逻辑，避免
        # 一次额外的 Python 方法调用。效果上和 ``super().__init__(env)`` 一致。
        self.env = env
        self.callbacks: EventCallbacks = []
        self._value = value
        # 字段：Timeout 等待的仿真时长。
        self._delay = delay
        # Timeout 默认就是成功事件，_ok 恒为 True。
        self._ok = True
        # 用 NORMAL 优先级调度；URGENT 仅留给中断和进程初始化。
        env.schedule(self, NORMAL, delay)

    def _desc(self) -> str:
        """
        返回包含延迟和可选结果值的延时事件描述，便于在调试日志里快速分辨
        不同 timeout。
        """
        value_str = '' if self._value is None else f', value={self.value}'
        return f'{self.__class__.__name__}({self._delay}{value_str})'


class Initialize(Event):
    """
    进程初始化事件。

    ``Process`` 创建后先生成该事件，并以紧急优先级调度，使生成器在被中断前先
    完成启动——这是"进程第一次 yield"的源头。
    """

    def __init__(self, env: Environment, process: Process):
        # 同样内联 Event.__init__ 的关键初始化逻辑以减少开销。
        self.env = env
        # 注意：callbacks 已经在构造时就挂上 ``process._resume``，所以这一步
        # 调度完成后下一个 step 就会触发进程第一次恢复。
        self.callbacks: EventCallbacks = [process._resume]
        self._value: Any = None

        # 进程初始化必须使用紧急优先级，保证生成器启动早于外部中断。
        # 否则可能出现"进程还没启动就被 interrupt"的竞态。
        self._ok = True
        env.schedule(self, URGENT)


class Interruption(Event):
    """
    进程中断事件。该事件把 ``Interrupt`` 异常投递给目标 ``Process``，用于抢占式
    资源或外部取消场景。
    """

    def __init__(self, process: Process, cause: Optional[Any]):
        # 同样内联 Event.__init__。
        self.env = process.env
        # callbacks 直接挂 ``self._interrupt``，由它在 step 时向目标进程注入异常。
        self.callbacks: EventCallbacks = [self._interrupt]
        # 中断是失败事件：_ok=False，_value 是 Interrupt 异常对象。
        # _defused=True 标记该失败已经在本层处理掉，Environment.step 不会再抛它。
        self._value = Interrupt(cause)
        self._ok = False
        self._defused = True

        if process._value is not PENDING:
            # 目标进程已经终止（_value 不再是 PENDING），此时中断无意义，直接报错。
            raise RuntimeError(f'{process} has terminated and cannot be interrupted.')

        if process is self.env.active_process:
            # 不允许自中断：当前活动进程不能在自己内部调用 ``self.interrupt()``，
            # 防止生成器在 yield 处形成不可恢复的死循环。
            raise RuntimeError('A process is not allowed to interrupt itself.')

        # 字段：需要被中断或恢复的目标进程。
        self.process = process
        # 用 URGENT 优先级，确保中断能"挤掉"普通业务事件先被处理。
        self.env.schedule(self, URGENT)

    def _interrupt(self, event: Event) -> None:
        """
        把 Interrupt 异常投递给目标进程。

        步骤：
        1. 目标进程已结束时忽略（可能与另一个中断并发触发）；
        2. 移除目标进程在原等待事件上的恢复回调，避免双重恢复；
        3. 调用 ``process._resume(self)``，把本 Interruption 事件作为参数传入，
           让 _resume 在 try/except 中以 throw 形式注入 Interrupt。
        """
        # 目标进程已经结束时忽略后续中断，避免并发中断重复处理。
        if self.process._value is not PENDING:
            return

        # 进程被中断时通常正等待某个目标事件，需要先移除原恢复回调，
        # 否则中断恢复 + 原事件恢复会让进程被 resume 两次。
        self.process._target.callbacks.remove(self.process._resume)

        # 把 Interruption 自身作为 event 传入 _resume。_resume 看到 _ok=False
        # 时会复制 event._value（即 Interrupt(cause)）作为 throw 给生成器。
        self.process._resume(self)


# 类型别名：进程生成器的签名——每次 yield 一个 Event，最终 send/throw 任意值。
ProcessGenerator = Generator[Event, Any, Any]


class Process(Event):
    """
    生成器进程包装器。它本身也是事件，负责驱动用户生成器不断 yield 下一个事件，
    并在目标事件完成后恢复生成器执行。
    """

    def __init__(self, env: Environment, generator: ProcessGenerator):
        if not hasattr(generator, 'throw'):
            # 实现说明：不同 Python 实现的生成器类型不同，因此这里采用能力检查
            # 而不是 ``inspect.isgenerator``。``throw`` 是生成器协议的方法，
            # 普通可迭代对象没有，调用前判断即可。
            raise ValueError(f'{generator} is not a generator.')

        # 同样内联 Event.__init__ 的关键初始化。
        self.env = env
        self.callbacks: EventCallbacks = []

        # 字段：被 Process 包装的 Python 生成器，业务流程通过 yield 事件暂停。
        self._generator = generator

        # 安排进程生成器首次执行。
        # 字段：当前进程正在等待的目标事件，目标完成后进程会继续恢复。
        # 用 Initialize 作为首次目标，Initialize 内部已挂好 ``process._resume``。
        self._target: Event = Initialize(env, self)

    def _desc(self) -> str:
        """
        返回包含生成器函数名的进程描述。日志里看到 ``Process(deploy_function)``
        比 ``Process()`` 直观得多。
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
        # 生成器对象的 ``__name__`` 就是定义时的函数名（yield 所在函数）。
        return self._generator.__name__  # type: ignore

    @property
    def is_alive(self) -> bool:
        """
        判断生成器是否仍未结束。``_value is PENDING`` 表示还没 StopIteration 也没抛异常。
        """
        return self._value is PENDING

    def interrupt(self, cause: Optional[Any] = None) -> None:
        """
        向当前进程发送中断请求，底层会创建 ``Interruption`` 事件。

        该方法只是把 Interruption 事件交给环境队列，**不会**立即 throw。真正的
        异常注入发生在 Interruption 被 step 处理时（见 ``Interruption._interrupt``）。
        """
        Interruption(self, cause)

    def _resume(self, event: Event) -> None:
        """
        恢复进程生成器执行：向生成器发送事件值或异常，接收下一个等待事件，并注册恢复回调。

        这是 SimPy 调度最核心的循环，每次目标事件完成都会被调用一次：
        1. 标记 ``env._active_proc = self``，便于资源 / 工具函数知道"当前是谁";
        2. 进入 while True，直到生成器 yield 出一个新事件或结束：
           - 成功事件 → ``generator.send(event._value)``；
           - 失败事件 → 复制异常后 ``generator.throw(exc)``；
           - 生成器 StopIteration → Process 成功；
           - 生成器抛 BaseException → Process 失败；
           - 生成器 yield 新事件 → 把 ``self._resume`` 挂到新事件的 callbacks；
        3. 清空 ``env._active_proc``。
        """
        # 标记当前正在恢复的活动进程。资源请求会用 ``env.active_process`` 记录
        # 请求发起者，所以这里必须在 send/throw 之前设置。
        self.env._active_proc = self

        while True:
            # 从生成器中取得下一步要等待的事件。
            try:
                if event._ok:
                    # 成功事件：把事件值作为 send 的返回值送进生成器。
                    event = self._generator.send(event._value)
                else:
                    # 失败事件：先标记异常已消解，避免 Environment.step 重复抛。
                    event._defused = True

                    # 为当前进程复制异常对象，避免多个进程共享同一回溯对象。
                    # （一个 Interrupt 被多个 Process 同时 throw 会让 __traceback__
                    # 互相污染；新建同类型异常并保留 cause 是最干净的方案。）
                    exc = type(event._value)(*event._value.args)
                    exc.__cause__ = event._value
                    event = self._generator.throw(exc)
            except StopIteration as e:
                # 进程生成器正常结束（return 或函数自然结束），Process 事件随之成功。
                event = None  # type: ignore
                # 字段：事件是否成功完成，失败事件会携带异常并在未消解时传播。
                self._ok = True
                # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
                # StopIteration 的 args 是生成器 ``return`` 的值；如果没 return 则为空元组。
                self._value = e.args[0] if len(e.args) else None
                self.env.schedule(self)
                break
            except BaseException as e:
                # 进程生成器抛出异常，Process 事件随之失败。
                event = None  # type: ignore
                self._ok = False
                # 去掉当前恢复函数的栈帧，使错误定位更贴近业务生成器。
                # 否则 traceback 会停留在 _resume 里，掩盖真正的 yield 行。
                e.__traceback__ = e.__traceback__.tb_next  # type: ignore
                self._value = e
                self.env.schedule(self)
                break

            # 生成器返回了新的等待事件。
            try:
                # 先按事件对象处理，若不是合法事件再构造错误提示。
                if event.callbacks is not None:
                    # 目标事件尚未处理，注册恢复回调等待其完成。
                    # 注意：这里采用"挂回调后退出循环"的模式，下一次该事件完成
                    # 时会再次进入本 _resume，event 参数就是它本身。
                    event.callbacks.append(self._resume)
                    break
            except AttributeError:
                # 生成器 yield 的不是合法事件，生成带源码位置的错误提示。
                if hasattr(event, 'callbacks'):
                    # 真的有 callbacks 属性但是 ``is not None`` 判断失败，说明业务
                    # 代码主动改成奇怪的东西，重新抛 AttributeError 给上层。
                    raise

                msg = f'Invalid yield value "{event}"'
                descr = _describe_frame(self._generator.gi_frame)  # type: ignore[attr-defined]
                raise RuntimeError(f'\n{descr}{msg}') from None

        # 退出循环后，更新 _target 为最新等待的事件或 None（已结束）。
        self._target = event
        # 清空活动进程标记，避免业务代码错误地读到过期的 active_process。
        self.env._active_proc = None


class ConditionValue:
    """
    组合条件事件的结果容器。

    它保存已经满足条件的原始事件，并提供字典式访问事件值的能力。注意：
    ``__hash__ = None`` 让实例**不可哈希**，避免被错误地当作 dict key。
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
            # 与另一个 ConditionValue 比较时按 events 列表逐个比对。
            return self.events == other.events
        elif isinstance(other, dict):
            # 与 dict 比较时把自身展开成 {event: value} 再比，便于测试断言。
            return self.todict() == other
        else:
            return NotImplemented

    # 显式置 None 让 ConditionValue 不可哈希，阻止它被当 dict key 使用。
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
    组合条件事件。

    它监听一组事件，并用 ``evaluate`` 函数判断何时完成；``AllOf`` 和 ``AnyOf``
    分别用它实现"全部完成"和"任一完成"。
    """

    def __init__(
        self,
        env: Environment,
        evaluate: Callable[[Tuple[Event, ...], int], bool],
        events: Iterable[Event],
    ):
        super().__init__(env)
        # 字段：组合条件判断函数，用于判断输入事件集合是否满足触发条件。
        # 签名：``evaluate(events_tuple, count) -> bool``，count 是已触发的事件数。
        self._evaluate = evaluate
        # 字段：组合条件监听的输入事件元组。tuple 而非 list，方便哈希和快速比较。
        self._events = tuple(events)
        # 字段：组合条件中已经完成并触发检查的事件数量。
        self._count = 0

        if not self._events:
            # 没有输入事件时条件立即成功——空集对 AllOf 和 AnyOf 都视为"已满足"。
            self.succeed(ConditionValue())
            return

        # 组合条件要求所有输入事件来自同一个仿真环境。跨环境混用会让 step
        # 时钟不一致，直接拒绝比静默错乱好。
        for event in self._events:
            if self.env != event.env:
                raise ValueError(
                    'It is not allowed to mix events from different environments'
                )

        # 为每个输入事件注册条件检查回调，已处理事件则立即检查。
        for event in self._events:
            if event.callbacks is None:
                # 事件已经处理完了——直接检查一次，避免错过已完成的事件。
                self._check(event)
            else:
                event.callbacks.append(self._check)

        # 条件触发后注册结果构造回调：把自己的 callbacks 里挂上 _build_value，
        # 这样 succeed() 之后 step 时会先把结果填进 ConditionValue。
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

        支持嵌套 Condition：递归展开子 Condition 收集到的所有原始事件。
        """
        for event in self._events:
            if isinstance(event, Condition):
                # 嵌套条件：递归收集其结果中保存的事件。
                event._populate_value(value)
            elif event.callbacks is None:
                # 普通事件且已处理，说明已经触发并把结果写入 _value。
                value.events.append(event)

    def _build_value(self, event: Event) -> None:
        """
        条件事件处理时移除检查回调，并在成功时构造条件结果。
        """
        self._remove_check_callbacks()
        if event._ok:
            # 字段：事件结果值；成功时为业务值，失败时通常为异常对象。
            # 这里只在成功路径填 ConditionValue；失败路径由 fail 写入异常对象。
            self._value = ConditionValue()
            self._populate_value(self._value)

    def _remove_check_callbacks(self) -> None:
        """
        递归移除输入事件上的检查回调，避免条件完成后留下循环引用。

        SimPy 资源对象也常这么干——条件 / 请求事件完成后及时清理 callbacks，
        防止事件图形成长链环导致 GC 不及时。
        """
        for event in self._events:
            if event.callbacks and self._check in event.callbacks:
                event.callbacks.remove(self._check)
            if isinstance(event, Condition):
                event._remove_check_callbacks()

    def _check(self, event: Event) -> None:
        """
        输入事件完成时检查组合条件是否满足，满足则触发条件事件。

        失败立即传播：任一输入事件失败，Condition 自身也失败并把原异常标
        ``_defused``（避免 Environment.step 重复抛）。
        """
        if self._value is not PENDING:
            # 已经触发过（成功或失败）的 Condition 不会再处理后续输入事件，
            # 否则会重复 fail/succeed 抛 "already triggered" 错。
            return

        self._count += 1

        if not event._ok:
            # 事件失败且异常未被消解时，环境需要把异常抛给调用方。
            event._defused = True
            self.fail(event._value)
        elif self._evaluate(self._events, self._count):
            # 条件满足后触发自身，结果值稍后由 _build_value 填充。
            # 注意这里 succeed() 不带参数，result 由 _build_value 在 step 时写入。
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

        注意：``count > 0 or len(events) == 0`` 这一写法同时处理了"非空且有一个完成"
        和"输入事件本身就是空集"两种情况；后者让 AnyOf 在空集下也能立即成功。
        """
        return count > 0 or len(events) == 0


class AllOf(Condition):
    """
    全部完成条件事件。

    只有输入事件全部成功触发后才成功，任一事件失败时立即失败（且原异常被消解，
    不再向 Environment.step 传播）。
    """

    def __init__(self, env: Environment, events: Iterable[Event]):
        super().__init__(env, Condition.all_events, events)


class AnyOf(Condition):
    """
    任一完成条件事件。

    输入事件中任意一个成功触发后即成功；任意事件失败会立刻向外传播（导致 AnyOf
    自身也失败）。
    """

    def __init__(self, env: Environment, events: Iterable[Event]):
        super().__init__(env, Condition.any_events, events)


def _describe_frame(frame: FrameType) -> str:
    """
    生成包含文件名、行号和代码行的错误定位文本，用于提示非法 yield 的位置。

    实现：打开生成器所在文件，扫描到 yield 所在行，把该行原文拼到异常信息里。
    这一步会比纯 traceback 更精确，因为 yield 报错时 traceback 通常还停留在
    Process._resume 里。
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
        # 文件读完没找到行号（理论上不应发生），退回基本格式。
        return f'  File "{filename}", line {lineno}, in {name}\n'