# 11 · 对象存储 store

> 对应源码：`simpy/resources/store.py`（164 行）

## 1. 职责

`store.py` 实现面向**离散对象项**的队列资源：

- `Store` —— 按 FIFO 保存对象
- `PriorityStore` —— 使用堆按优先级弹出对象
- `FilterStore` —— `get` 请求可指定过滤函数，只取满足条件的对象

faas-sim 中适合建模**请求队列、消息队列、任务缓冲区、负载均衡器内部等待队列**等。

## 2. 类继承关系

```
base.Put / base.Get
└── StorePut / StoreGet
        └── FilterStoreGet

base.BaseResource
└── Store
    ├── PriorityStore         # 用堆替换 put/get 行为
    └── FilterStore           # 在 _do_get 中按 filter 选择对象
```

附带：

- `PriorityItem`：`NamedTuple`，把 `priority` 与 `item` 绑定。

## 3. 模块公开符号

| 符号 | 类型 | 说明 |
| ---- | ---- | ---- |
| `StorePut` | 事件类 | Store 的入队事件 |
| `StoreGet` | 事件类 | Store 的出队事件 |
| `FilterStoreGet` | 事件类 | 带 `filter` 的出队事件 |
| `Store` | 资源类 | FIFO 离散对象队列 |
| `PriorityItem` | `NamedTuple` | 优先级对象包装器 |
| `PriorityStore` | 资源类 | 优先级对象队列 |
| `FilterStore` | 资源类 | 过滤式对象队列 |

## 4. `StorePut` / `StoreGet` / `FilterStoreGet`

### 4.1 `StorePut(base.Put)`

```python
class StorePut(base.Put):
    def __init__(self, store, item):
        self.item = item
        super().__init__(store)
```

- 字段 `item`：本次 put 携带的对象项。

### 4.2 `StoreGet(base.Get)`

```python
class StoreGet(base.Get):
    pass
```

不带额外字段；构造时由 `Store._do_get` 在 `succeed` 时填入实际取出的对象。

### 4.3 `FilterStoreGet(StoreGet)`

```python
class FilterStoreGet(StoreGet):
    def __init__(self, resource, filter=lambda item: True):
        self.filter = filter
        super().__init__(resource)
```

- 字段 `filter`：选择对象时使用的判定函数。默认接受所有对象。
- `FilterStore._do_get` 会遍历 `items`，取出第一个让 `event.filter(item)` 返回
  `True` 的对象。

## 5. `Store(base.BaseResource)`

### 5.1 构造

```python
class Store(base.BaseResource):
    def __init__(self, env, capacity=float('inf')):
        if capacity <= 0:
            raise ValueError('"capacity" must be > 0.')
        super().__init__(env, capacity)
        self.items: List[Any] = []
```

- `capacity`：可同时容纳的对象数；默认 `inf` 表示无上限。
- `items`：当前保存的对象列表（子类可能改为堆）。

### 5.2 公开方法（BoundClass 动态绑定）

| 方法 | 说明 |
| ---- | ---- |
| `store.put(item)` | 入队一个对象，返回 `StorePut` |
| `store.get()` | 出队一个对象，返回 `StoreGet`（`PriorityStore` 行为不变） |
| `store.get(filter=...)` | 仅 `FilterStore`：按过滤函数取对象 |

### 5.3 `_do_put(event)`

```python
def _do_put(self, event: StorePut) -> Optional[bool]:
    if len(self.items) < self._capacity:
        self.items.append(event.item)
        event.succeed()
    return None
```

- 容量未满时把对象 append 到 `items` 末尾并 `succeed()`。
- 容量满时不触发，返回 `None` 让请求留在 `put_queue` 等待。
- 返回 `None`（而非 `True`），是因为这里不需要在一次循环里连续触发多个 put——满了就
  停止本轮。

### 5.4 `_do_get(event)`

```python
def _do_get(self, event: StoreGet) -> Optional[bool]:
    if self.items:
        event.succeed(self.items.pop(0))
    return None
```

- 队列非空时 `pop(0)` 取出最早入队的对象（即 FIFO），作为 `event.value`。
- 队列空时返回 `None` 让请求留在 `get_queue` 等待。

## 6. `PriorityItem`

```python
class PriorityItem(NamedTuple):
    priority: Any
    item: Any

    def __lt__(self, other):
        return self.priority < other.priority
```

- 把优先级与对象绑成 `NamedTuple`，便于 `heapq` 使用。
- 比较规则：仅基于 `priority` 比较 `__lt__`；`item` 不参与大小判断。
- `Store` / `PriorityStore` 的 `items` 默认是 `list`；`PriorityStore` 的
  `_do_put` 改为 `heappush`，`_do_get` 改为 `heappop`，从而把 `list` 当堆用。

> 注意：直接 `put(PriorityItem(prio, obj))` 即可让对象按优先级出队；不要把
> `PriorityItem` 与未包装的对象混用。

## 7. `PriorityStore(Store)`

```python
class PriorityStore(Store):
    def _do_put(self, event: StorePut) -> Optional[bool]:
        if len(self.items) < self._capacity:
            heappush(self.items, event.item)
            event.succeed()
        return None

    def _do_get(self, event: StoreGet) -> Optional[bool]:
        if self.items:
            event.succeed(heappop(self.items))
        return None
```

- 完全复用 `Store` 的接口（`put(item)` / `get()`），仅替换内部数据结构的存取方式。
- `items` 默认是 `list`，但通过 `heappush` / `heappop` 操作，逻辑上表现为堆。
- 调用方应把"优先级 + 业务对象"用 `PriorityItem(prio, obj)` 包装后再 `put`。

## 8. `FilterStore(Store)`

```python
class FilterStore(Store):
    if TYPE_CHECKING:
        def get(self, filter=lambda item: True) -> FilterStoreGet: ...
    else:
        get = BoundClass(FilterStoreGet)

    def _do_get(self, event: FilterStoreGet) -> Optional[bool]:
        for item in self.items:
            if event.filter(item):
                self.items.remove(item)
                event.succeed(item)
                break
        return True
```

- `get(filter=...)` 返回 `FilterStoreGet`，可在请求级别指定过滤条件。
- `_do_get` 顺序遍历 `items`，找到第一个满足 `filter` 的对象后移除并返回。
- 总是返回 `True`，让基类继续遍历剩余 get 请求，因为一次过滤取出后其他 get 可能
  仍可满足（不同 filter 对应不同对象）。

## 9. faas-sim 使用示例

### 9.1 普通 FIFO 请求队列

```python
import simpy

env = simpy.Environment()
queue = simpy.Store(env, capacity=100)

def submit(req):
    yield queue.put(req)

def worker():
    while True:
        req = yield queue.get()
        yield env.timeout(req.runtime)
```

### 9.2 优先级队列

```python
prio_q = simpy.PriorityStore(env, capacity=100)

def submit_prio(req):
    yield prio_q.put(simpy.PriorityItem(priority=req.priority, item=req))

def worker_prio():
    while True:
        prio_item = yield prio_q.get()
        req = prio_item.item
        yield env.timeout(req.runtime)
```

### 9.3 过滤式队列

```python
typed_q = simpy.FilterStore(env, capacity=100)

# 仅取 type='cpu' 的请求
cpu_req = yield typed_q.get(lambda r: r.type == 'cpu')
# 取任意
any_req = yield typed_q.get()
```

适用场景：

- 请求队列 / 任务缓冲区
- 消息队列
- 负载均衡器内部按路由 / 类型分发
- 调度器中按优先级排序的待处理事件
