# SimPy 中文综合文档

本目录是基于 SimPy 官方文档重新整理的中文学习文档，不是官方站点逐页翻译。目标是把 SimPy 的核心概念、组成模块、入门方式、典型事件机制、资源模型和案例实践整理成一组清爽、连贯、适合源码阅读者使用的文档。

官方文档入口：

- SimPy 官方站点：<https://simpy.readthedocs.io/en/latest/>
- 官方入门教程：<https://simpy.readthedocs.io/en/latest/simpy_intro/>
- 官方主题指南：<https://simpy.readthedocs.io/en/latest/topical_guides/>
- 官方示例：<https://simpy.readthedocs.io/en/latest/examples/>
- 官方 API 参考：<https://simpy.readthedocs.io/en/latest/api_reference/>

## 文档结构

建议按以下顺序阅读：

1. [01_概念与组成.md](01_概念与组成.md)
   - 解释离散事件仿真、仿真时间、进程、事件、环境、资源等基础概念。
   - 说明 SimPy 为什么用 Python 生成器表达仿真过程。

2. [02_入门教程.md](02_入门教程.md)
   - 从最小示例开始，逐步介绍 `Environment`、`timeout()`、`process()`、`run()`、进程交互和事件等待。
   - 适合第一次写 SimPy 模型时参考。

3. [03_事件与进程机制.md](03_事件与进程机制.md)
   - 深入解释事件生命周期、事件值、回调、条件事件、进程中断、失败事件和常用工具函数。
   - 适合理解 SimPy 调度内核和源码。

4. [04_资源模型.md](04_资源模型.md)
   - 覆盖 `Resource`、`PriorityResource`、`PreemptiveResource`、`Container`、`Store`、`PriorityStore`、`FilterStore`。
   - 重点说明请求、排队、释放、容量、库存和对象流转。

5. [05_案例实战.md](05_案例实战.md)
   - 提供多个可运行案例：汽车充电、共享资源、银行排队超时、加油站、机器车间、生产者消费者、监控统计。
   - 每个案例都对应一类典型建模需求。

6. [06_源码阅读与工程实践.md](06_源码阅读与工程实践.md)
   - 解释官方文档内容如何映射到 SimPy 源码文件。
   - 说明在工程中使用 SimPy 时的建模边界、调试方法和常见坑。

7. [07_Python中高级语法与SimPy源码阅读.md](07_Python中高级语法与SimPy源码阅读.md)
   - 按由浅入深顺序讲解 SimPy 源码涉及的 Python 中高级语法。
   - 覆盖生成器、上下文管理器、回调、描述符、类型标注、运算符重载、堆队列等读源码必备知识。

## 这组文档覆盖的 SimPy 功能

| 功能类别 | 覆盖内容 |
| --- | --- |
| 仿真环境 | `Environment`、`now`、`run()`、`step()`、`peek()` |
| 进程 | 生成器进程、`env.process()`、进程作为事件、子进程等待 |
| 基础事件 | `Event`、`Timeout`、`Process`、`succeed()`、`fail()` |
| 条件事件 | `AnyOf`、`AllOf`、`event1 | event2`、`event1 & event2` |
| 中断 | `Process.interrupt()`、`simpy.Interrupt`、抢占资源 |
| 共享资源 | `Resource`、请求、释放、队列、公平性 |
| 优先级资源 | `PriorityResource`、`PreemptiveResource`、抢占原因 |
| 连续容量 | `Container`、`get()`、`put()`、液体/库存/能量建模 |
| 对象存储 | `Store`、`PriorityStore`、`FilterStore` |
| 实时仿真 | `RealtimeEnvironment` |
| 工具函数 | `start_delayed()`、`subscribe_at()` |
| 监控 | 资源队列、使用量、等待时间、吞吐量、事件日志 |

## 使用说明

这些文档适合三种用途：

- 快速学习 SimPy：从 `01` 到 `05` 顺序阅读。
- 阅读源码：重点看 `01`、`03`、`04`、`06`、`07`。
- 写仿真案例：直接参考 `05` 的案例模板，并按自己的业务实体替换过程、资源和统计指标。

如果项目中已有 `examples` 目录，可以把 `05_案例实战.md` 中的案例拆成独立脚本；如果只需要文档说明，保留当前 Markdown 即可。
