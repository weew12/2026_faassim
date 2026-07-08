# 10 · 槽位资源 resource

对应源码：`simpy/resources/resource.py`

## 1. 文件定位

`Resource` 系列建模有限并发槽位。最常见的理解是“信号量”：容量为 N，同一时刻最多 N 个进程持有资源。

## 2. Resource

核心状态：

| 字段 | 含义 |
| --- | --- |
| `capacity` | 并发槽位数 |
| `users` | 已获得槽位的请求 |
| `queue` | 等待槽位的请求，等同于 `put_queue` |

申请资源：

```python
with resource.request() as req:
    yield req
    ...
```

释放资源：

```python
resource.release(req)
```

`with` 退出时会自动 release，除非是生成器关闭阶段的 `GeneratorExit`。

## 3. PriorityResource

`PriorityResource` 使用 `PriorityRequest` 和 `SortedQueue`。排序键：

```python
(priority, time, not preempt)
```

含义：

1. `priority` 越小越优先。
2. 同优先级按申请时间 FIFO。
3. 同时间下，允许抢占的请求更靠前。

注意：`PriorityResource` 只排序，不抢占。抢占由 `PreemptiveResource` 实现。

## 4. PreemptiveResource

当资源已满且新请求允许抢占时：

1. 找出当前 users 中 key 最大的请求，也就是优先级最低者。
2. 如果新请求 key 更小，移除低优先级用户。
3. 向被抢占进程发送 `Interrupt(Preempted(...))`。
4. 再调用父类 `_do_put` 尝试让新请求占用槽位。

## 5. Preempted

`Preempted` 是中断原因对象，包含：

| 字段 | 含义 |
| --- | --- |
| `by` | 抢占者进程 |
| `usage_since` | 被抢占者开始占用资源的仿真时间 |
| `resource` | 发生抢占的资源 |

被抢占进程可这样处理：

```python
try:
    with res.request(priority=5) as req:
        yield req
        yield env.timeout(10)
except simpy.Interrupt as intr:
    preempted = intr.cause
```

## 6. faas-sim 可用场景

- 函数副本 worker 并发槽
- GPU/TPU 独占资源
- 优先级请求队列
- 抢占式调度或高优先级任务打断低优先级任务

