# 02 · 核心引擎 core

对应源码：`simpy/core.py`

## 1. 文件定位

`core.py` 实现离散事件仿真的时间轴。它只做底层调度，不理解 FaaS、网络、函数或资源语义。

核心职责：

- 保存当前仿真时间 `Environment._now`
- 保存待处理事件堆 `Environment._queue`
- 按时间、优先级和事件编号推进事件
- 提供 `process`、`timeout`、`event`、`all_of`、`any_of` 这些常用构造器

## 2. 事件队列排序

事件以四元组进入堆：

```python
(time, priority, eid, event)
```

排序规则：

1. `time` 小的先执行。
2. 同一时间下，`priority` 小的先执行。`URGENT=0`，`NORMAL=1`。
3. 同一时间同一优先级下，`eid` 小的先执行，保证确定性 FIFO。

这就是 SimPy 能复现仿真结果的关键之一。

## 3. `BoundClass`

`BoundClass` 是一个描述符，用来把事件类绑定成实例方法。例如：

```python
env.timeout(5)
```

运行时等价于：

```python
Timeout(env, 5)
```

资源对象也复用同一机制，例如 `resource.request()`、`store.put(item)`。`bind_early()` 会在实例创建时提前绑定这些方法，减少仿真循环中的描述符解析开销。

## 4. `Environment.step()`

`step()` 只推进一个事件：

```text
heappop(_queue)
  -> _now = event_time
  -> 取出 event.callbacks 并置空
  -> 依次调用 callback(event)
  -> 若事件失败且未 defused，抛出异常副本
```

两个细节很重要：

- `callbacks` 会在执行前置为 `None`，这表示事件已被处理，也能防止回调执行期间重复修改列表。
- 失败事件如果没有 `_defused` 标记，环境会重新构造同类型异常再抛出，避免多个事件共享同一个 traceback。

## 5. `Environment.run()`

`run()` 是反复调用 `step()` 的循环。`until` 有三种用法：

| 用法 | 行为 |
| --- | --- |
| `run()` | 运行到事件队列耗尽 |
| `run(until=10)` | 在仿真时间 10 处创建一个紧急终止事件 |
| `run(until=event)` | 运行到指定事件完成，并返回事件值 |

`run(until=number)` 要求 `number > env.now`，否则会抛 `ValueError`。

## 6. 停止机制

`StopSimulation` 不是错误，而是内部控制流。`run(until=event)` 会把 `StopSimulation.callback` 挂到目标事件上。目标事件成功后 callback 抛出 `StopSimulation(event.value)`，`run()` 捕获它并返回结果。

## 7. 与 faas-sim 的关系

faas-sim 的 `sim.core.Environment` 继承这里的 `Environment`。因此所有业务流程最终都归结为：

```python
yield env.timeout(...)
yield env.process(...)
yield resource.request()
```

这些 yield 不是线程阻塞，而是把当前进程挂到事件回调列表，等待未来某个 `step()` 恢复。

