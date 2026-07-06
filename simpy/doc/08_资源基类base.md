# 08 · 资源基类 base

> 对应源码：`simpy/resources/base.py`（206 行）

## 1. 职责

`base.py` 抽象出所有资源**共同具有**的 put/get 请求模型。它本身不规定资源语义
（容量、槽位、队列），只规定：

- put/get 请求事件的生命周期（`Put` / `Get`）
- 资源抽象基类 `BaseResource` 的通用骨架：维护 put_queue / get_queue、维护
  `_capacity`、在状态变化时反复触发可满足的请求
- 队列接口约定：`PutQueue` / `GetQueue` 类变量（默认 `list`，子类可替换为
  `SortedQueue` 等）

`Resource` / `Container` / `Store` 都建立在这一机制之上，**本文件是 SimPy 资源系统
的通用调度骨架**。

## 2. 模块内公开符号

| 符号 | 类型 | 说明 |
| ---- | ---- | ---- |
| `ResourceType` | `TypeVar` | 资源自身的泛型 |
| `Put` | 事件类 | 通用 put 请求事件（`ContextManager`） |
| `Get` | 事件类 | 通用 get 请求事件（`ContextManager`） |
| `PutType` / `GetType` | `TypeVar` | 子类化时使用的请求事件泛型 |
| `BaseResource` | 抽象基类 | 资源通用骨架 |

## 3. `Put(Event, ContextManager)` —— put 请求事件

```python
class Put(Event, ContextManager['Put'], Generic[ResourceType]):
    def __init__(self, resource: ResourceType):
        super().__init__(resource._env)
        self.resource = resource
        self.proc = self.env.active_process
        resource.put_queue.append(self)
        self.callbacks.append(resource._trigger_get)
        resource._trigger_put(None)
```

字段：

- `resource`：当前请求所属资源对象。
- `proc`：发起该请求的活动进程（用于调试与抢占）。

构造时同步做了三件事：

1. 把请求挂入 `resource.put_queue`。
2. 把 `resource._trigger_get` 挂到自己的 `callbacks`（说明：put 完成后**可能**让
   get 队列有机会被触发）。
3. 调用 `resource._trigger_put(None)`：资源立刻尝试满足该 put 请求。

### 3.1 上下文管理器

```python
def __enter__(self): return self

def __exit__(self, exc_type, exc_value, traceback):
    self.cancel()
    return None

def cancel(self):
    if not self.triggered:
        self.resource.put_queue.remove(self)
```

`Put` 实现了 `ContextManager`，因此可以用 `with resource.put(...) as req:` 形式
自动取消未触发的请求，避免遗忘清理。

## 4. `Get(Event, ContextManager)` —— get 请求事件

```python
class Get(Event, ContextManager['Get'], Generic[ResourceType]):
    def __init__(self, resource: ResourceType):
        super().__init__(resource._env)
        self.resource = resource
        self.proc = self.env.active_process
        resource.get_queue.append(self)
        self.callbacks.append(resource._trigger_put)
        resource._trigger_get(None)
```

结构与 `Put` 对称：

- 挂入 `resource.get_queue`。
- 把自己 `callbacks` 挂上 `resource._trigger_put`（get 完成后**可能**让 put 队列
  有机会被触发）。
- 立即调用 `resource._trigger_get(None)`。

`__exit__` / `cancel` 与 `Put` 一致：从 `get_queue` 移除未触发请求。

## 5. `BaseResource(PutType, GetType)` —— 资源抽象基类

### 5.1 类变量（队列类型）

```python
class BaseResource(Generic[PutType, GetType]):
    PutQueue: ClassVar[Type[MutableSequence]] = list
    GetQueue: ClassVar[Type[MutableSequence]] = list
```

子类可覆盖这两个类变量，把等待队列替换成自定义实现（如 `PriorityResource` 用
`SortedQueue`，见 `10_槽位资源resource.md`）。

### 5.2 构造

```python
def __init__(self, env, capacity):
    self._env = env
    self._capacity = capacity
    self.put_queue: MutableSequence[PutType] = self.PutQueue()
    self.get_queue: MutableSequence[GetType] = self.GetQueue()
    BoundClass.bind_early(self)
```

字段含义见 `07_资源子包总览.md` 第 5 节。`BoundClass.bind_early(self)` 提前把所有
`BoundClass` 描述符绑定成 `MethodType`，减少仿真循环开销。

### 5.3 公开方法（BoundClass 动态绑定）

| 方法 | 返回类型 | 说明 |
| ---- | -------- | ---- |
| `resource.put(...)` | `Put` | 创建 put 请求（子类可覆盖成 `ContainerPut` / `StorePut` 等） |
| `resource.get(...)` | `Get` | 创建 get 请求（子类可覆盖） |

> 注：`BaseResource` 本身只提供不带参数的 `put()` / `get()`。子类（如 `Container.put(amount)` /
> `Store.put(item)`）会重新声明带参的同名方法，覆盖此签名。

### 5.4 必须由子类实现的钩子

```python
def _do_put(self, event: PutType) -> Optional[bool]:
    raise NotImplementedError(self)

def _do_get(self, event: GetType) -> Optional[bool]:
    raise NotImplementedError(self)
```

- `_do_put(event)`：检查 `event` 当前能否满足，能满足则更新资源状态并
  `event.succeed()`，返回 `True` 表示可继续处理后续请求；不能则返回 `None`。
- `_do_get(event)`：与 `_do_put` 对称。

子类**只**需要实现这两个钩子，所有队列遍历和事件触发逻辑都集中在基类。

### 5.5 `_trigger_put(get_event)`

```python
def _trigger_put(self, get_event):
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
```

要点：

- 顺序遍历 `put_queue`，对每个未触发请求调用 `_do_put`。
- 若请求被触发，从队列弹出（同时验证队列不变量）。
- `_do_put` 返回 `None` / `False` 时**立刻停止遍历**，留给后续状态变化再触发；
  返回 `True` 时继续尝试下一个。
- 通过这种"一次循环内连续触发"的策略，能正确处理"一次 put 满足多个排队 get"等
  链式依赖。

### 5.6 `_trigger_get(put_event)`

与 `_trigger_put` 对称，遍历 `get_queue` 并调用 `_do_get`。

## 6. 子类覆盖示例（对应 09/10/11）

| 子类 | `_do_put` | `_do_get` | 队列 |
| ---- | --------- | --------- | ---- |
| `Container` | 容量剩余 ≥ amount 时增加水位 | 水位 ≥ amount 时减少水位 | `list` |
| `Resource` | 当前 users 不足 capacity 时占用槽位 | 从 users 移除对应 request | `list` |
| `PriorityResource` | 同 `Resource` | 同 `Resource` | `SortedQueue`（按 `key`） |
| `PreemptiveResource` | 满载时可抢占低优先级用户 | 同 `PriorityResource` | `SortedQueue` |
| `Store` | items 数量 < capacity 时入队 | items 非空时出队 | `list` |
| `PriorityStore` | items < capacity 时入堆 | 堆非空时出堆 | `list`（内部即堆） |
| `FilterStore` | 同 `Store` | 找到第一个满足 filter 的对象 | `list` |

## 7. faas-sim 衔接点

faas-sim 通常**不直接使用 `BaseResource`**，而是通过子类（`Resource` / `Container` /
`Store`）建模：worker 池、缓存水位、请求队列等。理解本文件的 put/get 协议是阅读
子类代码的前提。
