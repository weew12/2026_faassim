# sim 源码阅读文档

本目录用于放置 `sim` 包的源码阅读辅助文档。`sim` 是 faas-sim 的业务仿真层，基于 SimPy 提供的离散事件机制，实现 FaaS 平台、函数部署、副本生命周期、请求生成、调度、资源监控、指标记录和 Oracle 估计等功能。

建议先阅读 `simpy/sitedoc/07_Python中高级语法与SimPy源码阅读.md`，理解底层事件、进程和资源机制，再阅读这里的 `sim` 业务层语法教程。

## 文档列表

1. [07_Python中高级语法与sim源码阅读.md](07_Python中高级语法与sim源码阅读.md)
   - 面向只掌握基础 Python 的读者，解释通读 `sim` 源码需要的中高级语法。
   - 覆盖 `yield from`、抽象基类、枚举、`NamedTuple`、`dataclass`、双下划线字段、`defaultdict`、`Counter`、Pandas/Numpy、日志、异常边界和业务协程链路。

## 阅读顺序

推荐按以下顺序读源码：

1. `sim/faas/core.py`：先理解 FaaS 领域对象。
2. `sim/core.py`：理解业务环境 `Environment` 如何扩展 SimPy 环境。
3. `sim/faas/system.py`：理解部署、调用、扩缩容和调度队列。
4. `sim/faassim.py`：理解一次仿真实验如何装配和启动。
5. `sim/requestgen.py`：理解请求到达模型。
6. `sim/resource.py` 和 `sim/metrics.py`：理解资源状态与指标记录。
7. `sim/oracle/oracle.py`：理解经验数据、采样和估计器。
8. `sim/skippy.py`、`sim/topology.py`、`sim/docker.py`：理解外部系统适配。
