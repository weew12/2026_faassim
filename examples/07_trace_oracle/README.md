# trace_oracle：faas-sim trace-driven 执行时间样例

本样例用于演示 trace-driven / oracle-style 的函数执行时间建模方式。样例从 CSV 文件读取函数执行时间轨迹，并在函数 invoke 阶段按 trace 样本控制执行时间。

## 运行方式

将 `trace_oracle/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/07_trace_oracle/main.py
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
examples/07_trace_oracle/outputs/
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

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造两个函数部署；
5. 配置 trace-driven 模拟器；
6. 运行请求负载；
7. 导出 trace 和调用结果指标。

### `traces/function_runtime_trace.csv`

函数执行时间轨迹文件。

字段包括：

```text
function_name
sample_id
duration
```

### `oracle.py`

执行时间 Oracle 文件。

该文件提供：

```text
TraceRuntimeOracle
TraceSample
```

用于读取 CSV trace，并按照函数名称返回执行时间样本。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
TraceOracleSimulatorFactory
TraceOracleFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
sample = self.oracle.sample(function_name)
yield env.timeout(sample.duration)
```

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `trace_oracle_sample`、`invocations`、`schedule` 等指标，并生成输入 trace 摘要、实际取样摘要和调用摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
