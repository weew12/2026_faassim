# `sim` 包入口与模块边界

## 1. 对应源码

- `sim/__init__.py`
- `sim/faas/__init__.py`
- `sim/oracle/__init__.py`
- `sim/data/__init__.py`

## 2. 为什么先看包入口

包入口通常不实现复杂业务，但它定义了源码的公共边界。阅读入口文件可以判断：

- 哪些类型被设计为外部调用接口；
- 哪些模块只应在包内部使用；
- 使用者写 `from sim import ...` 或 `from sim.faas import ...` 时实际得到什么；
- 是否存在导入时初始化、副作用或循环依赖风险。

当前 `sim` 的核心实现分散在多个子模块中，入口文件主要承担命名空间组织职责，而不是启动仿真。

## 3. 顶层 `sim` 包

顶层包代表完整仿真框架，其主要组成如下：

```text
sim/
├── core.py          全局 Environment 与节点状态
├── faassim.py       仿真装配和运行入口
├── benchmark.py     实验工作负载协议
├── requestgen.py    请求到达过程
├── resource.py      资源状态与监控
├── metrics.py       指标记录
├── logging.py       日志后端与时钟
├── topology.py      网络拓扑
├── skippy.py        调度器适配
├── docker.py        镜像仓库与拉取
├── net.py           网络流
├── degradation.py   性能退化输入
├── hpa.py           HPA 风格伸缩
├── faas/            FaaS 领域对象和系统行为
└── oracle/          各类性能估计器
```

顶层入口应保持轻量。创建仿真通常从 `sim.faassim.Simulation` 开始，而不是依赖导入包时自动创建全局对象。

## 4. `sim.faas` 子包

`sim.faas` 是业务核心，分成三类内容：

| 文件 | 职责 |
|---|---|
| `core.py` | 数据模型、状态枚举、接口和基础负载均衡器 |
| `system.py` | `DefaultFaasSystem` 以及部署、启动、调用、传输过程 |
| `scaling.py` | 请求速率、平均值、队列和空闲伸缩过程 |
| `watchdogs.py` | 具体容器/watchdog 执行语义 |

这种拆分遵循“模型与行为分离”：`core.py` 说明系统中有哪些对象，`system.py` 说明对象如何变化。

## 5. `sim.oracle` 子包

Oracle 是仿真中的估计服务。它根据历史数据、拟合分布、节点与镜像属性等信息回答：

- 容器启动大约需要多久；
- 某函数在某节点上的执行时间是多少；
- 某条链路可用带宽是多少；
- 部署或执行的资源成本是多少；
- CPU、内存、GPU 等资源利用率如何估计。

Oracle 与执行器的边界必须清楚：Oracle **预测或查询数值**，真正推进仿真时间的是调用它的 SimPy 进程。

## 6. `sim.data` 子包

`sim/data` 用于组织仿真所需的数据文件及数据包入口。即使其 `__init__.py` 很小，也不应把大量业务逻辑塞入其中。数据读取、路径解析和估计逻辑应由使用数据的模块负责。

## 7. 导入建议

在业务代码中优先从定义对象的明确模块导入，例如：

```python
from sim.faassim import Simulation
from sim.faas.core import Function, FunctionDeployment
from sim.requestgen import function_trigger
```

明确导入有三点好处：

1. 阅读者能直接定位定义位置；
2. 减少包入口调整造成的影响；
3. 更容易识别 `core`、`system`、`resource` 等模块之间的依赖。

## 8. 阅读检查点

读完本章后，应能回答：

- 启动完整仿真应进入哪个模块？
- FaaS 的声明模型与运行行为分别位于哪里？
- 调度、资源和性能估计分别由哪个模块负责？
- 为什么 Oracle 返回的时间数值不会自动推进 SimPy 时钟？
