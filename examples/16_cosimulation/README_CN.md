# cosimulation：faas-sim 协同仿真样例

本样例用于演示 faas-sim 与外部控制/环境模型之间的协同仿真组织方式。它提供一个最小模板：外部 trace 周期性更新环境状态，faas-sim 函数模拟器读取该状态，并据此改变函数执行时间。

## 运行方式

将 `cosimulation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cosimulation/main.py
```

## 文件结构

```text
cosimulation/
├── inputs/
│   └── external_environment_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── context.py
├── controller.py
├── external_model.py
├── main.py
├── README_CN.md
└── simulator.py
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
examples/cosimulation/outputs/
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

## 后续扩展

该样例属于通用扩展功能样例。后续可以在此基础上继续扩展：

1. 将 trace-driven 控制器替换为强化学习控制器；
2. 将外部环境模型替换为网络仿真器；
3. 用 socket / 文件 / HTTP 接口与外部进程实时交换状态；
4. 将控制动作映射为真实扩缩容或调度决策；
5. 构建缓存状态感知调度与外部工作负载演化的联合仿真。
