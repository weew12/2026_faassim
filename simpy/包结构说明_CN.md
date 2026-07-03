# simpy 内置离散事件仿真子包结构说明

本目录来自用户上传的 `simpy-master.zip` 中的 `src/simpy` 源码，已作为 faas-sim 根目录下的独立 Python 子包合入，用于替换原先通过 `simpy==3.0.11` 安装的外部依赖。

## 文件职责

- `__init__.py`：聚合 SimPy 常用公开类，使调用方可以直接使用 `simpy.Environment`、`simpy.Timeout`、`simpy.Resource` 等入口。
- `core.py`：实现离散事件环境 `Environment`，维护仿真时间、事件堆队列、事件调度、单步推进和完整运行循环。
- `events.py`：实现 `Event`、`Timeout`、`Process`、`Condition`、`AllOf`、`AnyOf` 等事件和进程抽象。
- `exceptions.py`：定义 SimPy 异常层次，重点是进程中断异常 `Interrupt`。
- `resources/base.py`：定义共享资源的通用 put/get 队列框架。
- `resources/container.py`：实现连续容量资源 `Container`，适合表达水位、令牌、缓存容量等连续数量。
- `resources/resource.py`：实现有限并发槽位资源、优先级资源和抢占式资源。
- `resources/store.py`：实现 FIFO、优先级和过滤式对象队列。
- `rt.py`：实现与真实墙钟时间同步的实时仿真环境。
- `util.py`：提供延迟启动进程、事件订阅等进程编排辅助函数。

## 与 faas-sim 的关系

faas-sim 的 `sim.core.Environment` 继承并扩展 SimPy `Environment`，在其中挂载 FaaS 系统、网络拓扑、调度器、指标器和后台进程。函数副本生命周期、请求执行、镜像下载、资源监控和自动伸缩器都通过 `env.process(...)` 与 `env.timeout(...)` 推进，因此 SimPy 是 faas-sim 的仿真时钟和事件循环基础。
