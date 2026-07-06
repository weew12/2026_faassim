# resource_monitor：faas-sim 原生 ResourceMonitor 资源监控样例

本样例用于演示 faas-sim 中 `ResourceState` 和 `ResourceMonitor` 的基本用法，重点展示函数执行期间如何登记 CPU / 内存资源占用，以及如何导出资源监控结果。

## 运行方式

将 `resource_monitor/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/resource_monitor/main.py
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

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造函数部署；
5. 运行请求负载；
6. 导出资源监控和调用结果指标。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
ResourceMonitorSimulatorFactory
ResourceMonitorFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
env.resource_state.put_resource(...)
env.resource_state.remove_resource(...)
```

从而让 ResourceMonitor 能够采集到资源使用变化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出资源监控、调用、调度和部署生命周期相关指标，并生成摘要结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
