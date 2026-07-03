# 结果分析

仿真结果分析通过在仿真完成后提取 pandas DataFrame 完成，例如：

```python
sim.env.metrics.extract_dataframe(<name>)
```

Simulation 的 Environment 中包含一个 `Metrics` 对象。该对象贯穿整个仿真过程，用于记录事件。这些事件描述 FaaS 平台 `FaasSystem` 的不同方面，例如调度过程、数据流和函数调用。

## 默认日志

`FaasSystem` 的默认实现 `DefaultFaasSystem` 会记录以下过程的事件。这些事件可以使用对应名称提取为 DataFrame。

| 过程 | DataFrame 名称 |
| --- | --- |
| Allocation | `'allocation'` |
| Invocations | `'invocations'` |
| Scaling | `'scale'` |
| Scheduling | `'schedule'` |
| Function Replica Deployment | `'replica_deployment'` |
| Function Deployments | `'function_deployments'` |
| Function Deployment | `'function_deployment'` |
| Function Deployment lifecycle | `'function_deployment_lifecycle'` |
| Functions | `'functions'` |
| Flow | `'flow'` |
| Network | `'network'` |
| Node utilization | `'node_utilization'` |
| Function utilization | `'function_utilization'` |
| Function Execution Times | `'fets'` |

提示：项目在 `examples/analysis/main.py` 中提供了基础示例。每个 DataFrame 的具体字段含义可结合对应实现代码和后续分析逻辑进一步查看。

## Logging

仿真过程中会记录系统的多个方面。日志主要由核心实现产生，但也有一些部分留给用户根据自定义仿真器或自定义组件补充记录。

`Metrics` 定义了通用 `log` 函数，也提供了若干开箱即用的日志函数，用于记录 FaaS 平台生命周期中的特定事件。

`Metrics` 构造函数接收一个 `RuntimeLogger` 对象作为初始化参数。该 logger 负责存储所有记录，并可以通过传入 `Clock` 对象进行配置。`Clock` 决定每条日志事件对应的时间。

提示：可以查看 `sim.logging` 了解不同日志实现。
