# simpy 内置子包文档目录

> 本目录是对 `simpy/` 内置源码的逐文件解析索引。原来的总览文档
> `包结构说明_CN.md` 已按"一个文件/子包一个文档"的原则拆分到下面 11 个子文档，
> 原文件作为 legacy 保留在本目录下末尾。

## 0. 阅读顺序建议

| 阅读顺序 | 文档                                | 对应源码                  | 一句话定位 |
| -------- | ----------------------------------- | ------------------------- | ---------- |
| 1        | [01_simpy包入口](./01_simpy包入口.md)             | `simpy/__init__.py`        | 包聚合导出层，看 `import simpy` 能拿到什么 |
| 2        | [02_核心引擎core](./02_核心引擎core.md)            | `simpy/core.py`            | `Environment` 事件循环，是整个仿真时钟轴 |
| 3        | [03_事件与进程events](./03_事件与进程events.md)    | `simpy/events.py`          | `Event` / `Timeout` / `Process` / `Condition` 四大事件类 |
| 4        | [04_异常体系exceptions](./04_异常体系exceptions.md) | `simpy/exceptions.py`      | `SimPyException` 与 `Interrupt`，进程被中断的统一入口 |
| 5        | [05_实时仿真rt](./05_实时仿真rt.md)                | `simpy/rt.py`              | `RealtimeEnvironment`，可选的墙钟同步 |
| 6        | [06_工具函数util](./06_工具函数util.md)            | `simpy/util.py`            | `start_delayed` / `subscribe_at` 两个常用辅助 |
| 7        | [07_资源子包总览](./07_资源子包总览.md)             | `simpy/resources/__init__.py` | 三类资源抽象的入口说明 |
| 8        | [08_资源基类base](./08_资源基类base.md)            | `simpy/resources/base.py`  | `Put` / `Get` / `BaseResource` 通用 put/get 框架 |
| 9        | [09_容器资源container](./09_容器资源container.md)  | `simpy/resources/container.py` | `Container`，连续容量数值资源 |
| 10       | [10_槽位资源resource](./10_槽位资源resource.md)    | `simpy/resources/resource.py` | `Resource` / `PriorityResource` / `PreemptiveResource` |
| 11       | [11_对象存储store](./11_对象存储store.md)          | `simpy/resources/store.py` | `Store` / `PriorityStore` / `FilterStore` |

## 1. 模块依赖关系（自顶向下）

```
simpy                          # 包入口：聚合 re-export
├── core.Environment           # 事件循环、仿真时钟
├── events.*                   # Event / Timeout / Process / Condition / AllOf / AnyOf
├── exceptions.{SimPyException, Interrupt}
├── rt.RealtimeEnvironment     # Environment 的子类
├── util.{start_delayed, subscribe_at}
└── resources                  # 共享资源子包
    ├── base.{Put, Get, BaseResource}
    ├── container.Container
    ├── resource.{Resource, PriorityResource, PreemptiveResource}
    └── store.{Store, PriorityStore, FilterStore}
```

模块依赖方向（箭头表示"依赖"）：

```
core ──> events
events ──> exceptions
core ──> events          # core 引用 events 中的 Event/Timeout/Process 等
rt ──> core              # RealtimeEnvironment 继承 Environment
util ──> core + events   # 工具函数依赖环境与事件类型
resources.* ──> base     # 所有资源子类都基于 base.{Put, Get, BaseResource}
resources.* ──> core     # BoundClass / Environment
```

## 2. 公开对象清单（与 `simpy.__all__` 对齐）

由 `simpy/__init__.py` 通过 `__all__` 聚合导出，对外暴露以下对象：

| 类别 | 名称 | 实际来源 |
| ---- | ---- | -------- |
| Environments | `Environment` / `RealtimeEnvironment` | `core.py` / `rt.py` |
| Events | `Event` / `Timeout` / `Process` / `AllOf` / `AnyOf` | `events.py` |
| Resources | `Resource` / `PriorityResource` / `PreemptiveResource` / `Container` / `Store` / `PriorityStore` / `FilterStore` / `PriorityItem` | `resources/*.py` |
| Exceptions | `SimPyException` / `Interrupt` | `exceptions.py` |

对 faas-sim 调用方而言，`import simpy` 之后可直接使用上述全部对象，无需感知底层包内文件分布。

## 3. 与 faas-sim 的关系（顶层视角）

faas-sim 的 `sim.core.Environment` 继承并扩展了 `simpy.Environment`，把 FaaS 系统
相关的"函数部署、实例生命周期、请求执行、自动伸缩、网络传输"全部挂载为 SimPy
进程与事件。其调用约定保持 `env.process(...)`、`env.timeout(...)` 不变，因此本
目录对源码的逐文件解析同时适用于：

- 直接使用 `simpy` 写小型仿真
- 通过 `sim.core.Environment` 写 FaaS 仿真
- 阅读 faas-sim 任意业务模块，理解其调度原语
