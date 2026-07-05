# resource_monitor：faas-sim 原生 ResourceMonitor 资源监控样例

本样例用于演示 faas-sim 中 `ResourceState` 和 `ResourceMonitor` 的基本用法，重点展示函数执行期间如何登记 CPU / 内存资源占用，以及如何导出资源监控结果。

## 运行方式

将 `resource_monitor/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/resource_monitor/main.py
```

## 文件结构

```text
resource_monitor/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
└── simulator.py
```

## 样例目标

该样例主要回答以下问题：

1. 函数执行期间如何向 `env.resource_state` 登记 CPU / memory；
2. 函数执行结束后如何释放资源；
3. `ResourceMonitor` 如何周期性采集资源状态；
4. 如何从 `sim.env.metrics` 中导出资源监控 DataFrame；
5. 如何结合调用指标和资源指标分析函数运行过程。

## 实验设计

样例部署一个函数：

```text
resource-heavy-python-pi
```

该函数保持 2 个副本，并触发 12 个请求。每次请求执行期间会登记：

```text
CPU：节点 CPU 容量的 35%
Memory：128 MiB
执行时间：1.5 个仿真时间单位
```

请求结束后，CPU 和内存资源会从 `env.resource_state` 中释放。

## 输出文件

运行结束后，结果会保存到：

```text
examples/resource_monitor/outputs/
```

主要包括：

```text
resource.csv
resources.csv
resource_monitor.csv
resource_state.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
resource_monitor_summary.csv
resource_monitor_invocation_summary.csv
```

说明：不同 faas-sim 版本中的资源监控指标名称可能不同，因此本样例会同时尝试导出 `resource`、`resources`、`resource_monitor`、`resource_state`，实际存在的文件以运行结果为准。

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 多函数资源竞争；
2. 不同资源请求大小对调度结果的影响；
3. 节点级资源利用率曲线；
4. 资源监控与自动伸缩联动；
5. 资源监控与缓存替换策略联动。
