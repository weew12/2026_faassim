# fault_model：faas-sim 故障模型样例

本样例用于演示如何在 faas-sim 中构造简单、可复现的故障模型。样例不修改 faas-sim 核心代码，而是在函数执行模拟器中引入故障判定逻辑，并通过自定义指标记录请求成败与故障原因。

## 运行方式

将 `fault_model/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/fault_model/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何定义节点不可用窗口；
2. 如何模拟函数副本瞬时失败；
3. 如何模拟网络退化导致的执行时间变长；
4. 如何将故障判定写入 `fault_model_probe.csv`；
5. 如何导出故障事件时间线；
6. 如何统计请求成功、失败和不同故障原因的分布。

## 故障模型

样例内置三类故障：

```text
node_outage             节点不可用窗口，请求快速失败
replica_error           周期性函数副本错误，请求快速失败
network_degradation     网络退化，请求仍成功但执行时间增加
```

其中 `node_outage` 和 `network_degradation` 由时间窗口触发，`replica_error` 按请求编号周期性触发。

## 重要说明

faas-sim 默认 `invocations.csv` 只记录调用耗时，不直接表达 HTTP 状态码或业务成败。因此本样例将请求成败记录在自定义指标中：

```text
fault_model_probe.csv
```

分析请求是否失败时，应优先查看 `fault_model_probe.csv` 中的：

```text
success
reason
active_fault
final_duration
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/fault_model/outputs/
```

主要包括：

```text
fault_model_probe.csv
fault_timeline.csv
fault_events.csv
fault_model_summary.csv
fault_reason_distribution.csv
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

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造函数部署；
5. 固定调度到目标节点；
6. 启动故障事件时间线；
7. 运行请求负载；
8. 导出故障与调用结果指标。

### `fault_model.py`

故障模型定义文件。

该文件提供：

```text
FaultEvent
FaultDecision
DeterministicFaultModel
```

用于描述故障窗口、判断请求是否受故障影响，并输出故障事件表。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
FaultModelSimulatorFactory
FaultModelFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
decision = self.fault_model.decide(env.now, request.request_id, node.name)
```

并将判定结果写入 `fault_model_probe`。

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把函数副本固定部署到目标节点，使故障窗口稳定影响请求。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `fault_model_probe`、`fault_timeline`、`invocations` 等指标，并生成故障摘要和原因分布。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
