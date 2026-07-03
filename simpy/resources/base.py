"""
SimPy 共享资源基础框架。

本文件抽象出所有资源共同具有的 put/get 请求模型。资源操作并不直接返回结果，而是
返回一个 SimPy 事件：当资源条件满足时事件成功，等待该事件的进程继续执行。
``BaseResource`` 维护 put 队列和 get 队列，并在资源状态变化时反复尝试触发可满足的
请求。

Resource、Container 和 Store 都建立在这一机制之上，因此本文件是 SimPy 资源系统的
通用调度骨架。
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

ResourceType = TypeVar('ResourceType', bound='BaseResource')


class Put(Event, ContextManager['Put'], Generic[ResourceType]):
    """
    通用 put 请求事件。资源子类使用它表达“向资源放入/申请某种状态”的请求，请求无法立即完成时会停留在 put 队列。
    """

    def __init__(self, resource: ResourceType):
        super().__init__(resource._env)
        # 字段：该请求操作所属的资源对象。
        self.resource = resource
        # 字段：发起当前资源请求的活动进程。
        self.proc: Optional[Process] = self.env.active_process

        resource.put_queue.append(self)  # pyright: ignore
        self.callbacks.append(resource._trigger_get)
        resource._trigger_put(None)

    def __enter__(self) -> Put:
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
        取消未触发的 put 请求，并从资源 put 队列移除。
        """
        if not self.triggered:
            self.resource.put_queue.remove(self)  # pyright: ignore


class Get(Event, ContextManager['Get'], Generic[ResourceType]):
    """
    通用 get 请求事件。资源子类使用它表达“从资源取出/释放某种状态”的请求，请求无法立即完成时会停留在 get 队列。
    """

    def __init__(self, resource: ResourceType):
        super().__init__(resource._env)
        self.resource = resource
        self.proc = self.env.active_process

        resource.get_queue.append(self)  # pyright: ignore
        self.callbacks.append(resource._trigger_put)
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


PutType = TypeVar('PutType', bound=Put)
GetType = TypeVar('GetType', bound=Get)


class BaseResource(Generic[PutType, GetType]):
    """
    共享资源抽象基类。它统一维护 put/get 队列，并把具体资源规则下放给 _do_put 与 _do_get 实现。
    """

    PutQueue: ClassVar[Type[MutableSequence]] = list
    # 字段说明：put 请求队列类型，子类可替换为排序队列等实现。

    GetQueue: ClassVar[Type[MutableSequence]] = list
    # 字段说明：get 请求队列类型，子类可替换为排序队列等实现。

    def __init__(self, env: Environment, capacity: Union[float, int]):
        # 字段：资源绑定的仿真环境。
        self._env = env
        # 字段：资源容量上限。
        self._capacity = capacity
        # 字段：等待 put 条件满足的请求队列。
        self.put_queue: MutableSequence[PutType] = self.PutQueue()
        # 字段：等待 get 条件满足的请求队列。
        self.get_queue: MutableSequence[GetType] = self.GetQueue()

        BoundClass.bind_early(self)

    @property
    def capacity(self) -> Union[float, int]:
        """
        返回资源容量上限。
        """
        return self._capacity

    if TYPE_CHECKING:

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
        put = BoundClass(Put)
        get = BoundClass(Get)

    def _do_put(self, event: PutType) -> Optional[bool]:
        """
        由子类实现具体 put 条件判断和状态更新。
        """
        raise NotImplementedError(self)

    def _trigger_put(self, get_event: Optional[GetType]) -> None:
        """
        遍历 put 队列，持续尝试触发当前资源状态下可完成的 put 请求。
        """

        # 维护队列不变量：队列中只能保留尚未触发的请求。
        # 队列接口刻意保持最小，只依赖 append、pop、索引和长度。
        idx = 0
        while idx < len(self.put_queue):
            put_event = self.put_queue[idx]
            proceed = self._do_put(put_event)
            if not put_event.triggered:
                idx += 1
            elif self.put_queue.pop(idx) != put_event:
                raise RuntimeError('Put queue invariant violated')

            if not proceed:
                break

    def _do_get(self, event: GetType) -> Optional[bool]:
        """
        由子类实现具体 get 条件判断和状态更新。
        """
        raise NotImplementedError(self)

    def _trigger_get(self, put_event: Optional[PutType]) -> None:
        """
        遍历 get 队列，持续尝试触发当前资源状态下可完成的 get 请求。
        """

        # 维护队列不变量：队列中只能保留尚未触发的请求。
        # 队列接口刻意保持最小，只依赖 append、pop、索引和长度。
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
