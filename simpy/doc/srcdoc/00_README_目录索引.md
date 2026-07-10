# simpy 源码阅读索引

本目录是 `simpy/` 内置子包的源码阅读手册。每篇文档对应一个源码文件或子包，目标是帮助读者理解事件循环、进程恢复和资源排队机制，而不是替代官方 API 文档。

## 1. 推荐阅读顺序

| 顺序 | 文档 | 源码 | 阅读目标 |
| --- | --- | --- | --- |
| 1 | [01_simpy包入口](./01_simpy包入口.md) | `simpy/__init__.py` | 了解 `import simpy` 暴露哪些对象 |
| 2 | [02_核心引擎core](./02_核心引擎core.md) | `simpy/core.py` | 理解事件队列、仿真时钟、`run/step` |
| 3 | [03_事件与进程events](./03_事件与进程events.md) | `simpy/events.py` | 理解 `Event`、`Timeout`、`Process`、条件事件 |
| 4 | [04_异常体系exceptions](./04_异常体系exceptions.md) | `simpy/exceptions.py` | 理解 `Interrupt` 如何进入生成器 |
| 5 | [05_实时仿真rt](./05_实时仿真rt.md) | `simpy/rt.py` | 理解仿真时间与墙钟时间同步 |
| 6 | [06_工具函数util](./06_工具函数util.md) | `simpy/util.py` | 理解延迟启动和事件订阅工具 |
| 7 | [07_资源子包总览](./07_资源子包总览.md) | `simpy/resources/__init__.py` | 总览资源模型 |
| 8 | [08_资源基类base](./08_资源基类base.md) | `simpy/resources/base.py` | 理解 put/get 队列骨架 |
| 9 | [09_容器资源container](./09_容器资源container.md) | `simpy/resources/container.py` | 理解连续容量资源 |
| 10 | [10_槽位资源resource](./10_槽位资源resource.md) | `simpy/resources/resource.py` | 理解并发槽、优先级、抢占 |
| 11 | [11_对象存储store](./11_对象存储store.md) | `simpy/resources/store.py` | 理解 FIFO、优先级、过滤队列 |

## 2. 一张依赖图

```text
simpy.__init__
  ├─ core.Environment
  │    └─ events.{Event, Timeout, Process, Condition}
  │         └─ exceptions.Interrupt
  ├─ rt.RealtimeEnvironment ──继承──> core.Environment
  ├─ util ──使用──> core + events
  └─ resources
       ├─ base.{Put, Get, BaseResource}
       ├─ container.Container
       ├─ resource.{Resource, PriorityResource, PreemptiveResource}
       └─ store.{Store, PriorityStore, FilterStore}
```

## 3. 最核心的执行链

```text
env.process(generator)
  -> Process 创建 Initialize 事件
  -> Environment.step() 处理 Initialize
  -> Process._resume() 运行生成器到第一个 yield
  -> 生成器 yield Timeout / Resource request / Store get ...
  -> 目标事件完成后回调 Process._resume()
  -> 生成器继续运行
```

掌握这条链，就能读懂 faas-sim 中的部署、请求执行、监控循环和网络流。

## 4. 与 faas-sim 的连接点

- `sim.core.Environment` 继承 `simpy.Environment`。
- `Benchmark.run(env)` 通常是一个 SimPy 进程。
- 函数部署、调用、镜像拉取、网络传输都通过 `yield env.timeout(...)` 或 `yield env.process(...)` 推进。
- 请求队列、worker 池、缓存容量等可用 `Store`、`Resource`、`Container` 表达。

## 5. 阅读源码时最该关注的变量

| 变量 | 所在文件 | 含义 |
| --- | --- | --- |
| `Environment._queue` | `core.py` | 事件堆队列，排序键是 `(time, priority, eid)` |
| `Environment._now` | `core.py` | 当前仿真时间 |
| `Event.callbacks` | `events.py` | 事件完成时恢复哪些进程或条件 |
| `Event._value` | `events.py` | 事件结果；`PENDING` 表示未触发 |
| `Process._target` | `events.py` | 进程当前等待的事件 |
| `BaseResource.put_queue/get_queue` | `resources/base.py` | 未满足的资源请求队列 |

## 6. 三个核心状态机

### 6.1 Event 状态

```text
PENDING
  ├─ succeed(value) -> triggered(ok=True, value)
  ├─ fail(exc)      -> triggered(ok=False, exc)
  └─ trigger(other) -> copied state from other

triggered + Environment.step()
  -> callbacks 执行
  -> callbacks = None
  -> processed
```

读源码时要注意：`triggered` 和 `processed` 不是同一个概念。事件被 `succeed()` 后只是进入队列，只有 `Environment.step()` 处理完回调后才算 processed。

### 6.2 Process 状态

```text
Process 创建
  -> Initialize 事件进入队列
  -> 第一次 _resume
  -> generator yield target_event
  -> target_event.callbacks.append(_resume)
  -> target_event 完成
  -> 再次 _resume
  -> StopIteration: Process 成功
  -> BaseException: Process 失败
```

进程本身也是事件，所以可以 `yield process` 等待另一个进程结束。

### 6.3 Resource 请求状态

```text
request 创建
  -> 进入 put_queue/get_queue
  -> _trigger_put/_trigger_get 尝试满足
  -> 满足: event.succeed(...)
  -> 等待该请求的进程恢复
  -> release/get/put 可能触发另一侧队列重新检查
```

资源模型不是主动循环，而是由请求创建和请求完成回调驱动。

## 7. 常见源码阅读问题

### Q1: `yield env.timeout(1)` 为什么能暂停进程？

因为 `Process._resume()` 在生成器 yield 出 `Timeout` 后，会把自身 `_resume` 方法加入 `Timeout.callbacks`。Timeout 到时被 `Environment.step()` 处理，回调恢复进程。

### Q2: `event.succeed()` 是否立即恢复等待者？

不是。`succeed()` 只是写入结果并把事件 schedule 到环境队列。等待者会在之后某次 `step()` 执行 callbacks 时恢复。

### Q3: 为什么有 `_defused`？

失败事件如果没有被任何进程或条件处理，`Environment.step()` 会把异常抛给 `run()` 调用方。某些失败事件已经被业务处理过，例如 `Process._resume()` 把异常 throw 给生成器前会设置 `_defused=True`，防止环境重复抛出同一个异常。

### Q4: 为什么 `Interrupt` 也是事件驱动的？

为了保持所有状态变化都经过同一个事件队列。`interrupt()` 创建紧急事件，而不是立即打断生成器，这样同一仿真时间内的顺序仍由 `(time, priority, eid)` 决定。

### Q5: 为什么资源请求支持 `with`？

`Request.__exit__()` 会自动 `release()`，`Put/Get.__exit__()` 会自动取消未触发请求。这让进程被异常打断时不容易把资源请求永远留在队列里。

## 8. 调试建议

- 看时间推进：打印 `env.now`。
- 看队列是否空：看 `env.peek()` 是否为 `Infinity`。
- 看进程卡住在哪：看 `process.target`。
- 看事件是否已处理：看 `event.callbacks is None`。
- 看资源等待：看 `resource.queue`、`put_queue`、`get_queue`。
- 看抢占原因：捕获 `simpy.Interrupt` 并检查 `i.cause`。

## 9. faas-sim 中的典型映射

| faas-sim 概念 | SimPy 原语 | 说明 |
| --- | --- | --- |
| Benchmark 主流程 | `env.process(benchmark.run(env))` | 实验本身是一个进程 |
| 冷启动时间 | `env.timeout(...)` | 时间推进但不阻塞 Python 线程 |
| 镜像拉取 | `Process` + `Timeout` / Ether Flow | 网络流作为协程运行 |
| 调度 worker | `Process` | 常驻后台循环 |
| 请求队列 | `Store` / `PriorityStore` | 请求对象排队等待派发 |
| 副本并发槽 | `Resource` | 限制同一副本/节点并发 |
| 抢占 | `PreemptiveResource` + `Interrupt` | 高优先级任务打断低优先级任务 |
| 资源水位 | `Container` | 表示连续容量 |

## 10. 修改源码前的约束

- 不要改变 `Environment.schedule()` 的排序键，除非你清楚所有事件顺序后果。
- 不要让事件绕过 `succeed/fail/trigger` 私自改 `_value`，除非是在框架内部构造特殊事件。
- 修改 `Process._resume()` 前先写最小 smoke test，那里是最容易破坏语义的地方。
- 修改资源子类时不要在 `_do_put/_do_get` 中随意重排队列；队列不变量由基类检查。
- 保持公开 API 与 `simpy.__all__` 一致，避免 faas-sim 其他模块导入失败。

