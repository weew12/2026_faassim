# 03 · 事件与进程 events

> 对应源码：`simpy/events.py`（556 行）

## 1. 职责

`events.py` 定义离散事件仿真中的**基本执行单元**：

- `Event` —— 未来会完成的某个状态
- `Timeout` —— 经过一段仿真时间后自动完成
- `Initialize` / `Interruption` —— 进程初始化与中断专用事件
- `Process` —— 用 Python 生成器描述业务流
- `Condition` / `AllOf` / `AnyOf` —— 多事件组合

faas-sim 的**函数生命周期、请求执行、后台监控、调度器 worker、网络传输**都基于
这些事件实现非阻塞推进。

## 2. 模块级常量

```python
PENDING: object = object()             # 事件尚未产生结果时的唯一哨兵
EventPriority = NewType('EventPriority', int)
URGENT: EventPriority = EventPriority(0)   # 紧急优先级：中断、进程初始化
NORMAL: EventPriority = EventPriority(1)   # 普通优先级：多数业务事件
```

## 3. `Event`（事件基类）

### 3.1 状态机

事件在生命周期里有三种状态：

| 状态 | 判定 | 说明 |
| ---- | ---- | ---- |
| 未触发 | `self._value is PENDING` | 还在等待 |
| 已触发 / 待处理 | `self._value is not PENDING and self.callbacks is not None` | 已调用 `succeed/fail/trigger`，即将被 `step` 处理 |
| 已处理 | `self.callbacks is None` | 回调已执行完毕 |

### 3.2 字段

| 字段 | 类型 | 作用 |
| ---- | ---- | ---- |
| `env` | `Environment` | 事件所属仿真环境 |
| `callbacks` | `EventCallbacks` | 触发时要调用的回调列表（处理后置 `None`） |
| `_ok` | `bool` | 成功 / 失败标志 |
| `_value` | `Any` | 业务值（成功时）或异常对象（失败时） |
| `_defused` | `bool` | 失败事件的异常是否已被回调消解 |

### 3.3 属性

| 属性 | 含义 |
| ---- | ---- |
| `triggered` | 是否已触发 |
| `processed` | 是否已被环境处理 |
| `ok` | 成功标志（必须事件触发后才能读取） |
| `defused` / `defused.setter` | 标记失败异常已消解 |
| `value` | 读取触发后的结果值，未触发时抛 `AttributeError` |

### 3.4 触发方法

| 方法 | 行为 |
| ---- | ---- |
| `trigger(event)` | 把另一个事件的成功/失败状态和值复制到自身，再 `env.schedule(self)` |
| `succeed(value=None)` | 标记成功并把 `value` 写入 `_value`，调度进队列 |
| `fail(exception)` | 标记失败并把异常写入 `_value`，调度进队列 |
| `__and__(other)` / `__or__(other)` | 返回 `Condition`（分别对应 `all_events` / `any_events`） |

> 重复触发会抛 `RuntimeError`，传入非 `BaseException` 给 `fail` 会抛 `TypeError`。

## 4. `Timeout(Event)`

延时事件。创建时立即按 `delay` 调度到事件队列：

```python
class Timeout(Event):
    def __init__(self, env, delay, value=None):
        if delay < 0:
            raise ValueError(...)
        ...
        env.schedule(self, NORMAL, delay)
```

`_desc()` 会把 `delay` 与可选 `value` 拼到描述里，便于调试事件队列。

**faas-sim 用途**：镜像拉取耗时、冷启动、函数执行、监控周期等仿真耗时全部用
`env.timeout(...)` / `Timeout(env, ...)` 表达。

## 5. `Initialize(Event)`

进程初始化事件。`Process` 创建后第一件事就是构造 `Initialize`：

```python
self._target: Event = Initialize(env, self)
```

- `callbacks` 预先挂上 `process._resume`，使得进程第一次恢复时不需要先有别的事件
  完成。
- 用 `URGENT` 优先级调度，保证生成器**先于任何外部中断**完成启动。

## 6. `Interruption(Event)`

进程中断事件。`Process.interrupt(cause)` 内部会构造 `Interruption(process, cause)`：

- `_value = Interrupt(cause)`、`_ok = False`、`_defused = True`。
- 如果目标进程已经终止（`_value is not PENDING`），构造时直接抛 `RuntimeError`。
- 如果要中断的就是当前活动进程，构造时抛 `RuntimeError`（不允许自中断）。
- 用 `URGENT` 优先级调度。

`_interrupt(event)` 回调逻辑：

1. 若目标进程已结束，忽略。
2. 从原等待事件（`process._target`）的 `callbacks` 中移除恢复函数。
3. 调用 `process._resume(self)`，把 `Interrupt` 异常作为 `throw` 注入生成器。

## 7. `Process(Event)`

### 7.1 包装生成器

```python
class Process(Event):
    def __init__(self, env, generator):
        if not hasattr(generator, 'throw'):
            raise ValueError(f'{generator} is not a generator.')
        ...
        self._generator = generator
        self._target = Initialize(env, self)
```

`Process` 本身也是事件，它的完成代表生成器整体结束（成功返回或异常终止）。

### 7.2 重要属性

| 属性 | 含义 |
| ---- | ---- |
| `target` | 当前进程正在等待的目标事件 |
| `name` | 启动该进程的生成器函数名 |
| `is_alive` | 生成器是否仍未结束（`_value is PENDING`） |

### 7.3 公开方法

- `interrupt(cause=None)`：构造 `Interruption` 事件，由环境在下一轮 step 触发。

### 7.4 `_resume(event)` —— 核心循环

```python
while True:
    try:
        if event._ok:
            event = self._generator.send(event._value)
        else:
            event._defused = True
            exc = type(event._value)(*event._value.args)
            exc.__cause__ = event._value
            event = self._generator.throw(exc)
    except StopIteration as e:
        # 进程正常结束
        self._ok = True
        self._value = e.args[0] if e.args else None
        self.env.schedule(self)
        break
    except BaseException as e:
        # 进程异常退出，去掉恢复栈帧
        e.__traceback__ = e.__traceback__.tb_next
        self._ok = False
        self._value = e
        self.env.schedule(self)
        break

    # 生成器 yield 了一个新事件
    try:
        if event.callbacks is not None:
            event.callbacks.append(self._resume)
            break
    except AttributeError:
        # 生成器 yield 的不是合法事件
        raise RuntimeError(...) from None
```

要点：

- 成功事件 → `generator.send(value)`；失败事件 → 复制异常后 `generator.throw`。
- 进程结束（`StopIteration`）→ `Process` 事件成功；进程抛异常 → `Process` 事件失败。
- 生成器 yield 出新事件时，把 `_resume` 挂到该事件 `callbacks` 中，等待下次触发。
- 若 yield 的不是合法事件，借助 `_describe_frame` 把"文件名 + 行号 + 代码行"嵌入
  异常提示。

## 8. `ConditionValue` / `Condition` / `AllOf` / `AnyOf`

### 8.1 `ConditionValue`

组合条件事件的**结果容器**。包含：

- `events: List[Event]`：已经触发的事件列表
- `__getitem__` / `__contains__` / `__eq__` / `__hash__ = None` / `__repr__` /
  `__iter__` / `keys` / `values` / `items` / `todict`：字典式访问接口

注意：`__hash__ = None` 让实例**不可哈希**，避免被错误地当作 dict key。

### 8.2 `Condition(Event)`

通用组合条件事件：

```python
class Condition(Event):
    def __init__(self, env, evaluate, events):
        super().__init__(env)
        self._evaluate = evaluate
        self._events = tuple(events)
        self._count = 0
        ...
```

- `evaluate(events_tuple, count) -> bool`：由 `AllOf` / `AnyOf` 传入
  `Condition.all_events` / `Condition.any_events`。
- 输入事件必须来自同一个环境，否则 `raise ValueError(...)`。
- 输入为空时立刻 `succeed(ConditionValue())`。
- 给每个输入事件挂上 `_check` 回调；条件触发后由 `_build_value` 构造结果。
- `_check(event)`：
  - 任一输入事件失败 → 把异常标 `_defused` 并把当前 `Condition` 一起 `fail`。
  - `evaluate(...)` 返回 True → 当前 `Condition` `succeed()`，结果值稍后填。

### 8.3 `AllOf` / `AnyOf`

```python
class AllOf(Condition):
    def __init__(self, env, events):
        super().__init__(env, Condition.all_events, events)

class AnyOf(Condition):
    def __init__(self, env, events):
        super().__init__(env, Condition.any_events, events)
```

- `AllOf`：所有事件都成功才成功，任一失败即失败。
- `AnyOf`：任一事件成功即成功；只要有一个失败会立刻向外传播（fail）。

事件类还提供运算符语法：

```python
ev1 & ev2   # 等价于 Condition(env, Condition.all_events, [ev1, ev2])
ev1 | ev2   # 等价于 Condition(env, Condition.any_events, [ev1, ev2])
```

## 9. `_describe_frame(frame)`

辅助函数：把生成器抛出"非法 yield"时的文件名 + 行号 + 代码行打包成可读错误信息：

```
File ".../foo.py", line 42, in worker
    yield 123
Invalid yield value "123"
```

## 10. faas-sim 衔接示例（伪代码）

```python
def deploy_function(env, name, image):
    yield env.timeout(image.pull_time)        # 镜像拉取
    yield env.timeout(image.start_time)       # 冷启动
    while True:
        req = yield req_queue.get()           # 等请求
        env.process(handle(req))              # 处理请求

env = simpy.Environment()
env.process(deploy_function(env, ...))        # Process 包装
env.run(until=sim_time)                       # 推进仿真
```
