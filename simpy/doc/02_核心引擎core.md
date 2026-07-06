# 02 · 核心引擎 core

> 对应源码：`simpy/core.py`（258 行）

## 1. 职责

`core.py` 实现 faas-sim 运行时最关键的离散事件仿真环境。它只关心三件事：

1. **维护仿真时间**（`_now`）和**事件优先队列**（`_queue`）。
2. **推进事件**：每次 `step()` 取出下一个事件并触发回调。
3. **驱动整体仿真**：`run()` 持续推进直到队列耗尽、到达指定时间或指定事件完成。

faas-sim 中"函数副本部署、镜像拉取、启动 setup、请求执行、资源监控、自动伸缩器"
都以 SimPy 进程/事件挂载到该环境，因此本文件是整个仿真系统的**时间轴与调度循环**。

## 2. 公开符号一览

| 符号 | 类型 | 说明 |
| ---- | ---- | ---- |
| `Infinity` | 常量 | `float('inf')`，表示事件队列已无下一个事件 |
| `SimTime` | 类型别名 | `Union[int, float]` |
| `BoundClass` | 描述符工具 | 把事件/请求类绑定成环境或资源上的方法 |
| `EmptySchedule` | 异常 | 事件队列为空时抛出 |
| `StopSimulation` | 异常 | `run(until=...)` 用它跳出事件循环并携带返回值 |
| `Environment` | 类 | 离散事件仿真环境 |

## 3. `BoundClass`（描述符工具）

```python
class BoundClass(Generic[T]):
    def __init__(self, cls: Type[T])
    def __get__(self, instance, owner=None) -> Union[Type[T], MethodType]
    @staticmethod
    def bind_early(instance) -> None
```

- 把事件类（或请求类）包装成一个描述符，挂到 `Environment` 或 `Resource` 实例上，
  调用 `env.timeout(...)`、`env.process(...)` 时实际就是通过描述符返回
  `MethodType(cls, instance)`，**省去显式传 `env` 的样板**。
- `bind_early(instance)` 在实例化时立即把所有 `BoundClass` 字段绑定成 `MethodType`
  并写回实例属性，从而**减少仿真循环中反复解析描述符的开销**。`Environment.__init__`
  与所有 `BaseResource.__init__` 都会调用它。

## 4. `EmptySchedule` / `StopSimulation`

### 4.1 `EmptySchedule`

事件队列为空时 `step()` 会抛出。`run()` 捕获后认为仿真自然结束：

```python
except EmptySchedule:
    if until is not None:
        # 给了 until 但还没触发 ⇒ 异常退出
        raise RuntimeError(...)
```

### 4.2 `StopSimulation`

`run(until=event)` 时，框架会把 `StopSimulation.callback` 挂到该事件上。事件完成
时 callback 抛 `StopSimulation(event.value)`，从而跳出 `while step()` 循环，并把
事件结果作为 `run` 的返回值。

```python
@classmethod
def callback(cls, event):
    if event.ok:
        raise cls(event.value)
    else:
        raise event._value
```

## 5. `Environment`（核心）

### 5.1 字段

| 字段 | 类型 | 作用 |
| ---- | ---- | ---- |
| `_now` | `SimTime` | 当前仿真时间，由 `step()` 推进 |
| `_queue` | `List[Tuple[SimTime, EventPriority, int, Event]]` | 事件堆队列 |
| `_eid` | `count()` | 单调递增事件编号，决定同时间同优先级下的确定性顺序 |
| `_active_proc` | `Optional[Process]` | 当前正在执行的进程 |

### 5.2 动态绑定方法（`process` / `timeout` / `event` / `all_of` / `any_of`）

通过 `BoundClass` 把 5 个常用构造器绑定到环境实例上：

| 方法 | 返回类型 | 说明 |
| ---- | -------- | ---- |
| `env.process(generator)` | `Process` | 把生成器包装成 Process 并启动 |
| `env.timeout(delay, value=None)` | `Timeout` | 延时事件，表示冷启动、执行等耗时 |
| `env.event()` | `Event` | 手动触发事件，供进程间同步 |
| `env.all_of(events)` | `AllOf` | 等待所有事件完成 |
| `env.any_of(events)` | `AnyOf` | 等待任一事件完成 |

> 在 `TYPE_CHECKING` 分支里还提供了带类型签名的同名方法，作用是给 IDE / 类型检查器
> 显示正确的参数和返回值；运行时走 `else` 分支使用 `BoundClass` 形式。

### 5.3 `schedule(event, priority=NORMAL, delay=0)`

把事件按"目标时间 = `now + delay`、优先级、递增编号"压入堆队列：

```python
heappush(self._queue, (self._now + delay, priority, next(self._eid), event))
```

事件以三元组 `(time, priority, eid)` 排序，确保同时间同优先级下按事件编号（即创建
顺序）处理。

### 5.4 `peek() -> SimTime`

返回下一个事件的仿真时间；队列为空时返回 `Infinity`。该方法不弹出事件，只读取堆顶。

### 5.5 `step()`

推进**一个**离散事件：

1. `heappop` 取出队首事件，更新 `_now`。
2. 把 `event.callbacks` 暂存到局部变量并清空（防止处理过程中再次被修改）。
3. 依次执行回调。
4. 如果回调抛出 `StopSimulation`，把剩余未执行的回调重新挂回事件并以优先级 `-1`
   调度到队列，等待后续恢复运行。
5. 事件失败且异常未被消解（无 `_defused` 标记）时，由环境抛出**复制过**的异常
   （避免多个环境共享同一回溯）。

### 5.6 `run(until=None) -> Optional[Any]`

主循环：

```python
try:
    while True:
        self.step()
except StopSimulation as exc:
    return exc.args[0]
except EmptySchedule:
    ...
```

支持三种 `until` 形态：

| `until` 形态 | 行为 |
| ------------ | ---- |
| `None` | 跑到队列耗尽为止 |
| 数值（int/float） | 内部创建一个 `URGENT` 事件，在 `until` 时刻成功触发，从而通过 `StopSimulation` 退出 |
| `Event` | 挂 `StopSimulation.callback` 到该事件，事件完成后立即返回其 `value` |

`until` 是数值时必须 `> self.now`，否则 `raise ValueError`。

## 6. faas-sim 的衔接点

faas-sim 的 `sim.core.Environment` 继承本类并扩展：

- 维护 FaaS 资源池、函数副本、调度器。
- 通过 `env.process(...)` 启动副本生命周期、`env.timeout(...)` 推进冷启动和执行。
- 通过 `Resource` / `Store` / `Container` 表达请求并发和资源争用（详见 08-11）。

由于 `Environment` 的语义在子类中保持不变，faas-sim 的调用方可以无差别使用
`env.now`、`env.timeout`、`env.process` 等接口。
