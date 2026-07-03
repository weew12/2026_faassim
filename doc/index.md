# faas-sim 总览

![faas-sim 标识](_static/logo-h150.png)

faas-sim 是一个用于对容器化 Function-as-a-Service 平台进行 trace-driven 仿真的框架。它可用于开发和评估这类系统的运行管理策略，例如调度、自动伸缩、负载均衡以及其他平台运行机制。

## 架构

faas-sim 基于 [SimPy](https://simpy.readthedocs.io) 离散事件仿真框架构建。它使用 [Ether](https://github.com/edgerun/ether) 作为网络仿真层，同时借助 Ether 提供集群配置和网络拓扑来源。默认情况下，faas-sim 使用 [Skippy](https://github.com/edgerun/skippy-core) 调度系统进行 Serverless 资源调度；同时，用户可以插入自定义的调度器、自动伸缩器和负载均衡器。

faas-sim 采用 trace-driven 方式工作，使用真实负载和真实设备的 profiling 数据来模拟函数执行过程。项目预置了若干常见计算设备和代表性集群负载的 trace 数据，可用于快速启动实验。

![faas-sim 高层架构概览](figures/architecture-overview.png)

## 背景

faas-sim 由 [TU Wien](https://tuwien.at) 的 [Distributed Systems Group](https://dsg.tuwien.ac.at) 开发，属于围绕 Serverless Edge Computing 系统开展的一系列研究工作的一部分。

## 下一步阅读

- [核心概念](concepts/index.md)：理解 Function、FunctionImage、FunctionDeployment、FunctionContainer、FunctionReplica、Node、FaaS System、Function Simulator、Simulation 和 Request Generator。
- [系统实现](system/index.md)：理解 DefaultFaasSystem 的内部状态、调度队列、负载均衡器、部署记录和资源状态。
- [函数仿真器](function_sims/index.md)：理解 OpenFaaS HTTP/Forking Watchdog 风格仿真器。
- [结果分析](analysis/index.md)：理解 Metrics、日志事件和 DataFrame 提取。
