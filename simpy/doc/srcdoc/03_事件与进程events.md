# 03 · 事件与进程 events

对应源码：`simpy/events.py`

## 1. 文件定位

`events.py` 定义 SimPy 的基本执行单元：事件和进程。

- `Event`：一个未来会完成的状态。
- `Timeout`：经过一段仿真时间后自动成功的事件。
- `Process`：包装 Python 生成器，让业务逻辑可以 `yield event` 暂停。
- `Condition` / `AllOf` / `AnyOf`：组合多个事件。
- `Interruption`：把 `Interrupt` 异常投递给目标进程。

## 2. Event 的状态机

事件有三种状态：

| 状态 | 判定 | 含义 |
| --- | --- | --- |
| 未触发 | `_value is PENDING` | 还没有结果 |
| 已触发待处理 | `_value is not PENDING and callbacks is not None` | 已安排进事件队列，等待 `step()` 调回调 |
| 已处理 | `callbacks is None` | 回调已执行完 |

事件成功时 `_ok=True`，失败时 `_ok=False` 且 `_value` 通常是异常对象。

## 3. Timeout

`Timeout(env, delay, value)` 创建时会立即调度自己：

```python
env.schedule(self, NORMAL, delay)
```

因此 `yield env.timeout(5)` 的意思是：当前进程把恢复回调挂到这个 Timeout 上，5 个仿真时间单位后恢复。

## 4. Process 如何驱动生成器

`Process` 本身也是 `Event`。创建时会先创建一个 `Initialize` 事件，Initialize 的回调是 `process._resume`。

核心链路：

```text
Process(generator)
  -> Initialize 被 URGENT 调度
  -> step() 处理 Initialize
  -> _resume() 执行 generator.send(None)
  -> 生成器 yield 某个 Event
  -> 把 _resume 加到该 Event.callbacks
  -> 目标 Event 完成后再次 _resume
```

如果目标事件成功，`_resume()` 用 `generator.send(event._value)` 恢复；如果目标事件失败，则复制异常并用 `generator.throw(exc)` 恢复。

## 5. Interrupt 与 Interruption

`process.interrupt(cause)` 不会立即打断生成器，而是创建一个 `Interruption` 事件并以 `URGENT` 优先级调度。

当 Interruption 被处理时：

1. 从原目标事件的 callbacks 中移除 `process._resume`。
2. 调用 `process._resume(interruption_event)`。
3. `_resume()` 看到事件失败，于是把 `Interrupt(cause)` throw 进生成器。

这就是抢占式资源和事件订阅能中断进程的基础。

## 6. Condition / AllOf / AnyOf

`Condition` 监听一组输入事件，每个输入事件完成时调用 `_check()`：

- 任一输入事件失败：Condition 失败。
- `AllOf`：已完成数量等于输入事件数量时成功。
- `AnyOf`：至少一个输入事件完成时成功。

成功后 `_build_value()` 会构造 `ConditionValue`，可通过事件对象读取对应值。

## 7. 源码阅读重点

最值得细读的方法：

- `Event.succeed()` / `Event.fail()`：事件如何进入队列。
- `Process._resume()`：生成器如何被恢复。
- `Interruption._interrupt()`：中断如何替换原等待事件。
- `Condition._check()`：组合事件如何传播成功/失败。

