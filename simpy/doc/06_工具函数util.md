# 06 · 工具函数 util

> 对应源码：`simpy/util.py`（48 行）

## 1. 职责

`util.py` 提供与**进程编排**相关的辅助函数。它不改变核心事件机制，而是把常见的
事件组合写法封装成可复用函数：

- `start_delayed` —— 延迟启动一个进程
- `subscribe_at` —— 让当前进程订阅某个事件，被订阅事件触发时收到 `Interrupt`

## 2. `start_delayed(env, generator, delay) -> Process`

```python
def start_delayed(env, generator, delay):
    if delay <= 0:
        raise ValueError(f'delay(={delay}) must be > 0.')

    def starter() -> Generator[Event, None, Process]:
        yield env.timeout(delay)
        proc = env.process(generator)
        return proc

    return env.process(starter())
```

行为：

1. 校验 `delay > 0`，否则抛 `ValueError`。
2. 构造一个内部生成器 `starter`：先 `yield env.timeout(delay)`，再调用
   `env.process(generator)` 把目标生成器包装为 `Process`，并把该 `Process` 作为
   `starter` 的返回值。
3. 立刻把 `starter` 包装为 `Process` 返回，因此调用方拿到的"延迟启动器"也是一个
   `Process`，可以：

   - `yield start_delayed(...)` 等待它结束（返回时即目标进程已创建）。
   - `start_delayed(...).interrupt(...)` 在延迟期内取消启动。

使用示例：

```python
def worker(env, name):
    yield env.timeout(100)
    print(name, 'done')

p = start_delayed(env, worker(env, 'A'), delay=10)
# 仿真 10s 后才会真正启动 worker
```

## 3. `subscribe_at(event) -> None`

```python
def subscribe_at(event):
    env = event.env
    assert env.active_process is not None
    subscriber = env.active_process

    def signaller(signaller, receiver):
        result = yield signaller
        if receiver.is_alive:
            receiver.interrupt((signaller, result))

    if event.callbacks is not None:
        env.process(signaller(event, subscriber))
    else:
        raise RuntimeError(f'{event} has already terminated.')
```

行为：

1. 取当前活动进程作为订阅者 `subscriber`。**因此必须在进程内部调用**（即
   `env.active_process` 不为 `None`）。
2. 构造内部信号生成器 `signaller`：`yield event`（等待目标事件完成）→ 用
   `event._value` 作为业务结果 → 若订阅者仍存活就 `interrupt((event, result))`。
3. 当 `event` 已处理（`callbacks is None`）时直接抛 `RuntimeError`。
4. 否则把 `signaller` 包装为进程，由环境调度。

订阅者收到 `Interrupt` 后可通过 `cause` 拿到 `(event, result)` 元组：

```python
def watcher(env):
    try:
        yield env.timeout(1000)
    except simpy.Interrupt as i:
        signaller, result = i.cause
        print('signalled by', signaller, 'with', result)
```

## 4. 与核心原语的关系

| 工具函数 | 等价的核心写法 |
| -------- | -------------- |
| `start_delayed(env, gen, delay)` | 手工写一个 `def starter(): yield env.timeout(delay); return env.process(gen); env.process(starter())` |
| `subscribe_at(event)` | 手工写一个 `def signaller(event, sub): yield event; sub.interrupt((event, event.value))`，然后在 `subscribe_at` 处 `env.process(signaller(event, env.active_process))` |

工具函数只是把这些重复写法收拢成一行调用，本身不引入新事件类型。

## 5. faas-sim 使用建议

- **`start_delayed`**：用于"延迟创建副本"、"延迟启动监控任务"等场景，避免业务模块
  各自写 `starter()` 生成器。
- **`subscribe_at`**：用于"订阅另一个进程结束事件"等场景。比 `yield other_proc`
  （`Process` 也是 `Event`，可以直接 `yield` 等待）更显式，因为它会通过 `Interrupt`
  通知，避免订阅者错过时序。

> 注意：`subscribe_at` 通过 `Interrupt` 注入中断，业务模块需要在合适的地方捕获
> `Interrupt`，否则会触发 `Process` 失败（参见 `04_异常体系exceptions.md` 第 6 节）。
