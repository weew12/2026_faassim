# 10 · 槽位资源 resource

> 对应源码：`simpy/resources/resource.py`（231 行）

## 1. 职责

`resource.py` 实现类似**互斥锁 / 信号量**的资源对象。它把并发槽位抽象成可申请
（`request`）与释放（`release`）的事件，支持：

- `Resource` —— 限制同一时刻可持有资源的进程数量
- `PriorityResource` —— 等待队列按优先级排序
- `PreemptiveResource` —— 高优先级请求可抢占低优先级用户，并向被抢占进程发送 `Interrupt`

适用于模拟函数实例 worker 数、设备独占资源、连接池、GPU 等有限并发资源。

## 2. 类继承关系

```
base.Put / base.Get
└── Request / Release / PriorityRequest
    Request ← PriorityRequest
base.BaseResource
└── Resource
    └── PriorityResource
        └── PreemptiveResource
```

附带：

- `Preempted`：抢占原因对象
- `SortedQueue`：按 `key` 自动排序的 `list` 子类

## 3. 模块公开符号

| 符号 | 类型 | 说明 |
| ---- | ---- | ---- |
| `Preempted` | 普通类 | 抢占原因对象（`by` / `usage_since` / `resource`） |
| `Request` | 事件类 | Resource 的使用申请事件（带 `usage_since`） |
| `Release` | 事件类 | Resource 的释放事件 |
| `PriorityRequest` | 事件类 | 带优先级的资源申请事件 |
| `SortedQueue` | 类 | 按 `key` 排序的 `list` 子类 |
| `Resource` | 资源类 | 有限并发槽位 |
| `PriorityResource` | 资源类 | 优先级资源 |
| `PreemptiveResource` | 资源类 | 抢占式优先级资源 |

## 4. `Preempted`

```python
class Preempted:
    def __init__(self, by, usage_since, resource):
        self.by = by                       # 抢占者进程
        self.usage_since = usage_since     # 被抢占者开始占用资源的仿真时间
        self.resource = resource           # 资源对象
```

`PreemptiveResource` 抢占低优先级用户时，会把抢占者、被抢占者占用起始时间和资源
对象封装为 `Preempted`，再交给 `Interrupt(cause=Preempted(...))` 投递给被抢占进程。

## 5. `Request(base.Put)` —— 资源申请事件

```python
class Request(base.Put):
    resource: Resource
    usage_since: Optional[SimTime] = None  # 申请成功并开始占用资源的仿真时间

    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)
        if exc_type is not GeneratorExit:
            self.resource.release(self)
        return None
```

- 申请成功后，`Resource._do_put` 会写入 `usage_since = self._env.now`，便于统计
  "占用时长"。
- `__exit__` 默认会自动 `release(self)`（即 `with resource.request() as req:` 退出时
  自动释放），但当 `exc_type is GeneratorExit` 时**不**自动释放——避免生成器清理阶段
  在不合适的时机触发 release，形成不可回收的循环引用。

## 6. `Release(base.Get)` —— 资源释放事件

```python
class Release(base.Get):
    def __init__(self, resource, request):
        self.request = request
        super().__init__(resource)
```

- 释放时把对应 `Request` 从 `Resource.users` 移除（详见 `_do_get`）。
- 业务层通常不需要直接构造；要么通过 `with resource.request() as req:` 走
  `__exit__` 释放，要么调用 `resource.release(req)`。

## 7. `PriorityRequest(Request)`

```python
class PriorityRequest(Request):
    def __init__(self, resource, priority=0, preempt=True):
        self.priority = priority
        self.preempt = preempt
        self.time = resource._env.now
        self.key = (self.priority, self.time, not self.preempt)
        super().__init__(resource)
```

字段：

- `priority`：数值越小优先级越高。
- `preempt`：是否允许抢占当前资源用户。
- `time`：发起申请时的仿真时间，用于同优先级下的 FIFO 排序。
- `key`：综合排序键 `(priority, time, not preempt)`，被 `SortedQueue.append` 使用。

## 8. `SortedQueue(list)`

```python
class SortedQueue(list):
    def __init__(self, maxlen=None):
        super().__init__()
        self.maxlen = maxlen

    def append(self, item):
        if self.maxlen is not None and len(self) >= self.maxlen:
            raise RuntimeError('Cannot append event. Queue is full.')
        super().append(item)
        super().sort(key=lambda e: e.key)
```

- 继承 `list`，每次 `append` 后按 `e.key` 排序。
- 可选 `maxlen` 限制队列长度，满时抛 `RuntimeError`。
- 被 `PriorityResource` / `PreemptiveResource` 用作 `PutQueue`。

## 9. `Resource(base.BaseResource)`

### 9.1 构造与字段

```python
class Resource(base.BaseResource):
    def __init__(self, env, capacity=1):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')
        super().__init__(env, capacity)
        self.users: List[Request] = []
        self.queue = self.put_queue
```

- `capacity`：可同时占用的资源槽数（默认 1，类似互斥锁）。
- `users`：当前已获得资源槽的请求列表。
- `queue`：`put_queue` 的公开别名，便于业务层直接观察等待队列长度。

### 9.2 属性

- `count`：当前正在使用资源槽的请求数量（`len(self.users)`）。

### 9.3 公开方法（BoundClass 动态绑定）

| 方法 | 说明 |
| ---- | ---- |
| `resource.request()` | 申请一个资源槽，返回 `Request` |
| `resource.release(request)` | 释放指定已获得的资源槽，返回 `Release` |

### 9.4 `_do_put(event)`

```python
def _do_put(self, event: Request) -> None:
    if len(self.users) < self.capacity:
        self.users.append(event)
        event.usage_since = self._env.now
        event.succeed()
```

槽位未满时占用并 `succeed()`，否则留在队列等待。

### 9.5 `_do_get(event)`

```python
def _do_get(self, event: Release) -> None:
    try:
        self.users.remove(event.request)
    except ValueError:
        pass
    event.succeed()
```

把对应 `Request` 从 `users` 移除（找不到就忽略），然后 `succeed()`。

## 10. `PriorityResource(Resource)`

```python
class PriorityResource(Resource):
    PutQueue = SortedQueue
    GetQueue = list

    if TYPE_CHECKING:
        def request(self, priority=0, preempt=True) -> PriorityRequest: ...
        def release(self, request) -> Release: ...
    else:
        request = BoundClass(PriorityRequest)
        release = BoundClass(Release)
```

- 复用 `Resource` 的 `_do_put` / `_do_get`。
- 把 `PutQueue` 改为 `SortedQueue`，使等待请求按 `PriorityRequest.key` 自动排序。
- `request(priority=0, preempt=True)` 默认 `preempt=True`，但因为 `_do_put` 直接
  继承自 `Resource`，抢占实际由子类 `PreemptiveResource` 实现。

## 11. `PreemptiveResource(PriorityResource)`

```python
class PreemptiveResource(PriorityResource):
    users: List[PriorityRequest]

    def _do_put(self, event: PriorityRequest) -> None:
        if len(self.users) >= self.capacity and event.preempt:
            preempt = max(self.users, key=lambda e: e.key)
            if preempt.key > event.key:
                self.users.remove(preempt)
                preempt.proc.interrupt(
                    Preempted(
                        by=event.proc,
                        usage_since=preempt.usage_since,
                        resource=self,
                    )
                )
        return super()._do_put(event)
```

行为：

1. 当前槽位满且新请求允许抢占 → 找到现有 `users` 中 `key` 最大的（即优先级最低或
   抢占标志 `False`）用户。
2. 若该用户的 `key` 严格大于新请求的 `key`（即新请求优先级更高）→ 把它从 `users`
   移除并对其 `proc.interrupt(Preempted(...))`。
3. 不论是否真的抢占到用户，最后都调用 `super()._do_put(event)`：
   - 若刚才抢出空位，本步会成功占用。
   - 若没抢到且原本就没空位，则本步不会触发，事件保留在 `SortedQueue` 等待。

被中断的业务进程需要捕获 `Interrupt`，通过 `i.cause` 拿到 `Preempted`，自行决定
是否重试 / 退出。

## 12. faas-sim 使用示例

```python
import simpy

env = simpy.Environment()
# 1) 普通槽位资源：worker 池
pool = simpy.Resource(env, capacity=4)

def task(name, run_t):
    with pool.request() as req:
        yield req
        yield env.timeout(run_t)
        print(env.now, name, 'done')

# 2) 优先级资源：高优先级任务先拿槽位
prio_pool = simpy.PriorityResource(env, capacity=2)
yield prio_pool.request(priority=0)   # 高优先级

# 3) 抢占式资源：紧急任务可抢断低优先级
pre = simpy.PreemptiveResource(env, capacity=1)

def low_priority_user():
    try:
        with pre.request(priority=10) as req:
            yield req
            yield env.timeout(100)
    except simpy.Interrupt as i:
        preempted = i.cause
        print('low user preempted by', preempted.by)

def high_priority_arrival():
    yield env.timeout(20)
    with pre.request(priority=0) as req:    # 抢占
        yield req
        yield env.timeout(5)
```

适用场景：

- 函数实例 worker 数（CPU worker、GPU worker）
- 设备独占资源（独占磁盘、独占网卡）
- 连接池
- 任意需要并发槽位限制 + 可选优先级 / 抢占的仿真建模
