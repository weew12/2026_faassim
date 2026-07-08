# 06 · 工具函数 util

对应源码：`simpy/util.py`

## 1. 文件定位

`util.py` 提供两个进程编排辅助函数：

- `start_delayed(env, generator, delay)`
- `subscribe_at(event)`

它们不改变事件模型，只是封装常见写法。

## 2. start_delayed

作用：延迟启动一个生成器进程。

```python
proc_starter = start_delayed(env, worker(env), delay=5)
```

内部逻辑：

```text
starter 进程启动
  -> yield env.timeout(delay)
  -> env.process(generator)
  -> return proc
```

返回的是“启动器进程”，不是目标进程本身。`yield start_delayed(...)` 的返回值才是目标 `Process`。

## 3. start_delayed 的限制

`delay` 必须大于 0。零延迟没有必要，直接 `env.process(generator)` 即可。

## 4. subscribe_at

作用：让当前活动进程订阅某个事件。目标事件完成时，当前进程会被 `Interrupt` 唤醒。

必须在进程内部调用，因为它依赖 `env.active_process` 找到订阅者。

```python
def watcher(env, target):
    subscribe_at(target)
    try:
        yield env.timeout(100)
    except simpy.Interrupt as intr:
        event, result = intr.cause
```

## 5. subscribe_at 与 yield event 的区别

- `yield event`：当前进程直接等待目标事件。
- `subscribe_at(event)`：当前进程可以继续等待别的事件；目标事件完成时通过中断通知它。

这适合“我在做 A，但 B 完成时要通知我”的场景。

## 6. 常见错误

- 在进程外调用 `subscribe_at`：没有 active process，会断言失败。
- 订阅已经处理完的事件：会抛 `RuntimeError`。

