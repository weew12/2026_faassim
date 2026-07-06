# 09 · 容器资源 container

> 对应源码：`simpy/resources/container.py`（114 行）

## 1. 职责

`container.py` 实现 `Container`，用于表达**具有容量上限和当前水位的连续资源**：

- `put` 增加水位，`get` 消耗水位
- 当容量不足或剩余空间不足时，请求进入等待队列
- 适合表达缓存空间、带宽令牌、资源预算等连续数量，特别适用于"生产/消耗"关系的
  仿真场景

## 2. 类继承关系

```
base.Put / base.Get
└── ContainerPut / ContainerGet        # 带 amount 字段的请求事件

base.BaseResource
└── Container                          # 连续容量资源
```

## 3. 模块公开符号

| 符号 | 类型 | 说明 |
| ---- | ---- | ---- |
| `ContainerAmount` | `Union[int, float]` | 类型别名，连续数量 |
| `ContainerPut` | 事件类 | 增加容量的请求事件 |
| `ContainerGet` | 事件类 | 消耗容量的请求事件 |
| `Container` | 资源类 | 连续容量资源 |

## 4. `ContainerPut(base.Put)` / `ContainerGet(base.Get)`

### 4.1 共同点

- 构造时都要求 `amount > 0`，否则 `raise ValueError(...)`。
- 构造时调用 `super().__init__(container)`，从而触发 `base.Put` / `base.Get` 的
  注册流程（挂入队列、绑定 `_trigger_get` / `_trigger_put`）。

### 4.2 字段

| 类 | 字段 | 说明 |
| -- | ---- | ---- |
| `ContainerPut` | `amount` | 要增加的容量值 |
| `ContainerGet` | `amount` | 要消耗的容量值 |

## 5. `Container(base.BaseResource)`

### 5.1 构造与参数校验

```python
def __init__(self, env, capacity=inf, init=0):
    if capacity <= 0:
        raise ValueError('"capacity" must be > 0.')
    if init < 0:
        raise ValueError('"init" must be >= 0.')
    if init > capacity:
        raise ValueError('"init" must be <= "capacity".')
    super().__init__(env, capacity)
    self._level = init
```

| 参数 | 类型 | 默认 | 校验 |
| ---- | ---- | ---- | ---- |
| `capacity` | `ContainerAmount` | `float('inf')` | 必须 > 0 |
| `init` | `ContainerAmount` | `0` | 必须 0 ≤ init ≤ capacity |

### 5.2 字段

- `_level`：当前水位（私有），通过 `level` 属性只读暴露。

### 5.3 公开方法（BoundClass 动态绑定）

| 方法 | 说明 |
| ---- | ---- |
| `container.put(amount) -> ContainerPut` | 增加 `amount` 单位容量 |
| `container.get(amount) -> ContainerGet` | 消耗 `amount` 单位容量 |

### 5.4 `_do_put(event)`

```python
def _do_put(self, event: ContainerPut) -> Optional[bool]:
    if self._capacity - self._level >= event.amount:
        self._level += event.amount
        event.succeed()
        return True
    else:
        return None
```

- 当 `capacity - level ≥ amount` 时，增加水位并 `succeed()`。
- 不满足时返回 `None`，请求保留在 `put_queue` 等待后续 `_trigger_put` 重新检查。
- `_do_put` 返回 `True` 让基类继续处理后续 put 请求；返回 `None` 时基类
  `_trigger_put` 会停止遍历。

### 5.5 `_do_get(event)`

```python
def _do_get(self, event: ContainerGet) -> Optional[bool]:
    if self._level >= event.amount:
        self._level -= event.amount
        event.succeed()
        return True
    else:
        return None
```

与 `_do_put` 对称：当 `level ≥ amount` 时减少水位并成功。

## 6. 与基类（`base.py`）的衔接

`Container` 没有覆盖 `PutQueue` / `GetQueue`，因此默认使用 `list` 队列。`_do_put` /
`_do_get` 只关心"容量是否足够"这一最简单条件，没有优先级、抢占或过滤等其他语义。
若需要按优先级处理排队请求，需要继承 `Container` 并实现自定义 `_do_put` / 队列类型。

## 7. faas-sim 使用示例

```python
import simpy

env = simpy.Environment()
cache = simpy.Container(env, capacity=100, init=100)

def producer():
    while cache.level < 100:
        yield env.timeout(1)
        yield cache.put(10)

def consumer(env, name):
    while True:
        yield cache.get(20)
        yield env.timeout(2)
        print(env.now, name, 'processed; level=', cache.level)

env.process(producer())
for i in range(3):
    env.process(consumer(env, f'worker-{i}'))
env.run(until=50)
```

适用场景：

- 缓存容量 / 内存水位
- 带宽令牌（每请求消耗 N 令牌，定时补充）
- 燃料、资源预算
- 任何"产/消"关系的连续数量
