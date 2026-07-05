# trace_oracle：faas-sim trace-driven 执行时间样例

本样例用于演示 trace-driven / oracle-style 的函数执行时间建模方式。样例从 CSV 文件读取函数执行时间轨迹，并在函数 invoke 阶段按 trace 样本控制执行时间。

## 运行方式

将 `trace_oracle/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/trace_oracle/main.py
```

## 文件结构

```text
trace_oracle/
├── outputs/
├── traces/
│   └── function_runtime_trace.csv
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── oracle.py
├── README_CN.md
└── simulator.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何从 CSV trace 读取函数执行时间样本；
2. 如何构造一个轻量级 TraceRuntimeOracle；
3. 函数 invoke 阶段如何从 Oracle 中取样；
4. 不同函数如何使用不同执行时间轨迹；
5. 如何导出 trace 取样记录和函数调用结果。

## Trace 文件格式

样例使用：

```text
traces/function_runtime_trace.csv
```

字段如下：

```text
function_name,sample_id,duration
```

说明：

```text
function_name：函数名称
sample_id：样本序号
duration：本次执行时间，单位为仿真时间单位
```

## 实验设计

样例部署两个函数：

```text
trace-fast-python-pi   使用较短执行时间样本
trace-slow-python-pi   使用较长执行时间样本
```

在 invoke 阶段，模拟器从 `TraceRuntimeOracle` 中读取对应函数的下一个样本，并用该样本的 `duration` 作为本次请求执行时间。

## 输出文件

运行结束后，结果会保存到：

```text
examples/trace_oracle/outputs/
```

主要包括：

```text
trace_oracle_sample.csv
trace_input_summary.csv
trace_sample_summary.csv
trace_invocation_summary.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 使用真实函数运行日志作为 trace；
2. 引入不同节点上的执行时间差异；
3. 将 trace-driven 执行时间与冷启动时间建模结合；
4. 支持按请求类型、输入大小或节点类型选择 trace 样本；
5. 为论文中的仿真实验提供更接近真实系统的执行时间模型。
