# cosimulation：faas-sim 协同仿真样例

本样例用于演示 faas-sim 与外部控制/环境模型之间的协同仿真组织方式。它提供一个最小模板：外部 trace 周期性更新环境状态，faas-sim 函数模拟器读取该状态，并据此改变函数执行时间。

## 运行方式

将 `cosimulation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/16_cosimulation/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何把外部环境 trace 接入 faas-sim；
2. 如何构造一个外部控制循环；
3. 如何让外部状态影响函数执行时间；
4. 如何记录 faas-sim 与外部控制器之间的状态交换；
5. 如何导出协同仿真过程中的阶段、控制和调用指标。

## 外部 trace 格式

样例输入文件为：

```text
inputs/external_environment_trace.csv
```

字段包括：

```text
phase_name           外部阶段名称
start_time           阶段开始时间
duration             阶段持续时间
rps                  该阶段请求速率
runtime_factor       函数执行时间放大系数
network_delay        额外网络延迟
controller_action    外部控制动作
description          阶段说明
```

函数执行时间计算方式为：

```text
final_duration = base_duration * runtime_factor + network_delay
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/16_cosimulation/outputs/
```

主要包括：

```text
external_environment_trace.csv
cosim_exchange.csv
cosim_phase.csv
cosim_workload_phase.csv
cosim_invoke_probe.csv
cosim_phase_invoke_summary.csv
cosim_exchange_summary.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
resource.csv
resources.csv
resource_monitor.csv
resource_state.csv
```

## 结果解读

重点查看：

```text
cosim_exchange.csv
```

该文件记录外部控制器每个控制周期向 faas-sim 写入的外部状态。

```text
cosim_invoke_probe.csv
```

该文件记录每次函数调用读取到的外部阶段、控制动作、运行时间放大系数、网络延迟和最终执行时间。

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取外部环境 trace；
2. 创建共享协同仿真上下文；
3. 创建外部控制器；
4. 创建 faas-sim Simulation；
5. 启动请求负载和控制循环；
6. 导出协同仿真结果。

### `inputs/external_environment_trace.csv`

外部环境 trace 文件。

用于描述不同时段的请求速率、函数运行时间放大系数、额外网络延迟和控制动作。

### `context.py`

共享上下文文件。

该文件提供：

```text
ExternalPhase
CosimulationContext
```

用于在外部控制器和函数模拟器之间共享外部状态。

### `external_model.py`

外部模型文件。

该文件提供 `ExternalEnvironmentTrace`，负责读取 CSV trace 并按仿真时间查询当前外部阶段。

### `controller.py`

外部控制器文件。

该文件提供 `ExternalController`，按照固定控制周期更新共享上下文，并记录 `cosim_exchange` 和 `cosim_phase` 指标。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
CosimulationSimulatorFactory
CosimulationFunctionSimulator
```

其核心逻辑是在 `invoke()` 阶段读取共享上下文，并根据外部状态计算函数执行时间。

### `analysis.py`

指标导出与分析文件。

该文件负责导出协同仿真指标，并生成阶段级调用摘要和控制交换摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
