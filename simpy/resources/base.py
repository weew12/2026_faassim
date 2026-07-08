"""
SimPy 共享资源基础框架。

本文件抽象出所有资源共同具有的 put/get 请求模型。资源操作并不直接返回结果，而是
返回一个 SimPy 事件：当资源条件满足时事件成功，等待该事件的进程继续执行。
``BaseResource`` 维护 put 队列和 get 队列，并在资源状态变化时反复尝试触发可满足的
请求。

Resource、Container 和 Store 都建立在这一机制之上，因此本文件是 SimPy 资源系统的
通用调度骨架。

faas-sim 衔接：
- 函数副本 worker 池 → ``Resource`` / ``PriorityResource`` / ``PreemptiveResource``；
- 缓存水位 / 令牌桶 → ``Container``；
- 请求 / 消息 / 任务队列 → ``Store`` 系列；
- 上述资源都基于本文件的 put/get 框架，理解 ``_trigger_put`` / ``_trigger_get``
  的循环不变量是阅读子类实现的前提。
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    ClassVar,
    ContextManager,
    Generic,
    MutableSequence,
    Optional,
    Type,
    TypeVar,
    Union,
)

from simpy.core import BoundClass, Environment
from simpy.events import Event, Process

if TYPE_CHECKING:
    from types import TracebackType

# 资源自身的泛型，供 Put / Get 事件反向引用资源对象。
ResourceType = TypeVar('ResourceType', bound='BaseResource')


class Put(Event, ContextManager['Put'], Generic[ResourceType]):
    """
    通用 put 请求事件。

    资源子类使用它表达"向资源放入/申请某种状态"的请求，请求无法立即完成时会
    停留在 ``put_queue``。构造时挂上 ``resource._trigger_get`` 是因为 put 完成
    可能让原本因"资源空"而等待的 get 请求满足，需要触发 get 队列重检。
    """

    def __init__(self, resource: ResourceType):
        # 调用 Event.__init__ 初始化 env/callbacks/_value。
        super().__init__(resource._env)
        # 字段：该请求操作所属的资源对象。
        self.resource = resource
        # 字段：发起当前资源请求的活动进程。
        # 注意：如果当前没有活动进程（例如在环境初始化阶段构造请求），
        # 这里会得到 None——资源子类通常不要求 put 必须在进程内发起。
        self.proc: Optional[Process] = self.env.active_process

        # 把请求挂入 put 队列；pyright: ignore 抑制"未知属性"提示，因为
        # BaseResource.put_queue 的具体类型取决于子类。
        resource.put_queue.append(self)  # pyright: ignore
        # put 完成后**可能**让 get 队列有可满足请求，因此挂 _trigger_get 回调。
        self.callbacks.append(resource._trigger_get)
        # 立刻尝试满足该 put 请求；条件满足时事件会在本次 step 中触发。
        resource._trigger_put(None)

    def __enter__(self) -> Put:
        # 支持 ``with resource.put() as req:`` 形式，进入时不做事。
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        # with 块退出时自动取消未触发的请求，避免遗忘清理导致队列堆积。
        self.cancel()
        return None

    def cancel(self) -> None:
        """
        取消未触发的 put 请求，并从资源 put 队列移除。

        已触发的请求（triggered=True）不能再取消——已经被 step 处理过了。
        """
        if not self.triggered:
            self.resource.put_queue.remove(self)  # pyright: ignore


class Get(Event, ContextManager['Get'], Generic[ResourceType]):
    """
    通用 get 请求事件。

    资源子类使用它表达"从资源取出/释放某种状态"的请求，请求无法立即完成时会
    停留在 ``get_queue``。与 ``Put`` 对称，构造时挂 ``resource._trigger_put``
    是因为 get 完成可能让原本因"资源满"而等待的 put 请求满足。
    """

    def __init__(self, resource: ResourceType):
        super().__init__(resource._env)
        self.resource = resource
        self.proc = self.env.active_process

        resource.get_queue.append(self)  # pyright: ignore
        # get 完成后**可能**让 put 队列有可满足请求。
        self.callbacks.append(resource._trigger_put)
        # 立刻尝试满足该 get 请求。
        resource._trigger_get(None)

    def __enter__(self) -> Get:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self.cancel()
        return None

    def cancel(self) -> None:
        """
        取消未触发的 get 请求，并从资源 get 队列移除。
        """
        if not self.triggered:
            self.resource.get_queue.remove(self)  # pyright: ignore


# 子类化时使用的请求事件泛型，方便子类方法签名引用自身请求类型。
PutType = TypeVar('PutType', bound=Put)
GetType = TypeVar('GetType', bound=Get)


class BaseResource(Generic[PutType, GetType]):
    """
    共享资源抽象基类。

    它统一维护 put/get 队列，并把具体资源规则下放给 ``_do_put`` 与 ``_do_get`` 实现。
    子类只需关心"什么条件下算满足 + 满足时怎么改资源状态"，所有队列遍历、回调挂载、
    上下文管理都集中在基类。

    faas-sim 衔接：faas-sim 通常不会直接使用 ``BaseResource``，而是通过其子类
    ``Resource`` / ``Container`` / ``Store`` 建模。但所有这些子类的请求触发逻辑
    都来自本类的 ``_trigger_put`` / ``_trigger_get``。
    """

    # put 请求队列类型，子类可替换为排序队列等实现。
    # 例如 ``PriorityResource`` 把 PutQueue 替换为 ``SortedQueue``，使等待请求
    # 自动按 key 排序。ClassVar 让所有子类共享一份默认值。
    PutQueue: ClassVar[Type[MutableSequence]] = list

    # get 请求队列类型，子类可替换为排序队列等实现。
    GetQueue: ClassVar[Type[MutableSequence]] = list

    def __init__(self, env: Environment, capacity: Union[float, int]):
        # 字段：资源绑定的仿真环境。
        self._env = env
        # 字段：资源容量上限。语义由子类决定：Resource 是并发槽数、Container
        # 是连续容量、Store 是队列长度上限。
        self._capacity = capacity
        # 字段：等待 put 条件满足的请求队列。
        self.put_queue: MutableSequence[PutType] = self.PutQueue()
        # 字段：等待 get 条件满足的请求队列。
        self.get_queue: MutableSequence[GetType] = self.GetQueue()

        # 提前绑定 BoundClass 描述符——资源通常会重新声明 put/get 的具体签名
        # （例如 Container.put(amount)），但基类提供的无参版本依然可以走 bind_early。
        BoundClass.bind_early(self)

    @property
    def capacity(self) -> Union[float, int]:
        """
        返回资源容量上限。
        """
        return self._capacity

    if TYPE_CHECKING:
        # 仅静态类型检查分支：给 IDE / mypy 提示无参 put/get 的签名。
        # 运行时这里走 else 分支的 BoundClass 形式。

        def put(self) -> Put:
            """
            创建向资源提交 put 操作的事件。
            """
            return Put(self)

        def get(self) -> Get:
            """
            创建向资源提交 get 操作的事件。
            """
            return Get(self)

    else:
        # 运行时：BoundClass 动态绑定。子类（如 Container.put(amount) /
        # Store.put(item)）会用同名属性覆盖这里的无参版本。
        put = BoundClass(Put)
        get = BoundClass(Get)

    def _do_put(self, event: PutType) -> Optional[bool]:
        """
        由子类实现具体 put 条件判断和状态更新。

        返回值语义：
        - ``True``：本次 put 满足，循环可以继续尝试后续 put 请求；
        - ``None`` 或 ``False``：本次 put 未满足（或已满足但不应继续），循环停下。

        子类必须显式 ``raise NotImplementedError``，基类不提供默认实现。
        """
        raise NotImplementedError(self)

    def _trigger_put(self, get_event: Optional[GetType]) -> None:
        """
        遍历 put 队列，持续尝试触发当前资源状态下可完成的 put 请求。

        触发时机：每次有 get 事件完成（传入 ``get_event``）或新 put 请求入队时。
        ``get_event`` 参数当前未被使用，但保留为接口便于将来扩展（例如根据
        具体哪个 get 完成做优先级重排）。

        循环不变量：每次迭代后 ``self.put_queue[idx:]`` 中所有请求都尚未触发，
        已触发的请求必须已从队列中弹出。
        """
        # 维护队列不变量：队列中只能保留尚未触发的请求。
        # 队列接口刻意保持最小，只依赖 append、pop、索引和长度——子类可换成
        # 任意 ``MutableSequence`` 实现（包括 SortedQueue 这样的排序列表）。
        idx = 0
        while idx < len(self.put_queue):
            put_event = self.put_queue[idx]
            # 让子类判断该请求能否满足；若满足，子类负责 succeed() 并更新资源状态。
            proceed = self._do_put(put_event)
            if not put_event.triggered:
                # 请求没满足，下标前移去看下一个。
                idx += 1
            elif self.put_queue.pop(idx) != put_event:
                # 不变量被破坏：队列里的元素和我们刚看到的不是同一个。
                # 这通常意味着子类在 _do_put 里偷偷改了队列——直接抛错报警。
                raise RuntimeError('Put queue invariant violated')

            if not proceed:
                # 子类明确说"处理完这条就够了，不要继续尝试"——典型场景是某种
                # 资源配额被本次 put 吃满，剩下的 put 注定不满足。
                break

    def _do_get(self, event: GetType) -> Optional[bool]:
        """
        由子类实现具体 get 条件判断和状态更新。语义与 ``_do_put`` 对称。
        """
        raise NotImplementedError(self)

    def _trigger_get(self, put_event: Optional[PutType]) -> None:
        """
        遍历 get 队列，持续尝试触发当前资源状态下可完成的 get 请求。

        与 ``_trigger_put`` 对称，循环不变量也一样：每次迭代后
        ``self.get_queue[idx:]`` 中所有请求都尚未触发，已触发的必须已弹出。
        """
        # 维护队列不变量：队列中只能保留尚未触发的请求。
        idx = 0
        while idx < len(self.get_queue):
            get_event = self.get_queue[idx]
            proceed = self._do_get(get_event)
            if not get_event.triggered:
                idx += 1
            elif self.get_queue.pop(idx) != get_event:
                raise RuntimeError('Get queue invariant violated')

            if not proceed:
                break
