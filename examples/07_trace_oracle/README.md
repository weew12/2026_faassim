# 07_trace_oracle：faas-sim trace-driven 执行时间样例

本样例用于演示 trace-driven / oracle-style 的函数执行时间建模方式。样例从 CSV 文件读取函数执行时间轨迹，并在函数 invoke 阶段按 trace 样本控制执行时间。

## 运行方式

将 `07_trace_oracle/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/07_trace_oracle/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何从 CSV trace 读取函数执行时间样本；
2. 如何构造一个轻量级 TraceRuntimeOracle；
3. 函数 invoke 阶段如何从 Oracle 中取样；
4. 不同函数如何使用不同执行时间轨迹；
5. 如何验证 "每次 invoke 实际拿到的执行时间" 和 "trace 中派出的样本" 完全一致。

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
trace-fast-python-pi   使用较短执行时间样本（duration 0.08-0.13）
trace-slow-python-pi   使用较长执行时间样本（duration 0.45-0.62）
```

两个函数各自 1 个副本。`main.py` 分别触发 16 / 12 个请求：

```text
fast 函数：rps=8（每 0.125s 一个请求），16 次 invoke → 需要从 12 个 trace 样本中循环 2 次
slow 函数：rps=5（每 0.2s 一个请求），12 次 invoke → 恰好覆盖 trace 一个完整 cycle
```

> **trace 循环覆盖**：oracle 的 cursor 在 sample_id 达到末尾后自动回到 1。本样例的 fast 函数
> 因为实际 invoke 数 > trace 样本数，会触发循环覆盖（详见 `trace_cycle_summary.csv`）。

在 invoke 阶段，模拟器从 `TraceRuntimeOracle` 中读取对应函数的下一个样本，并用该样本的 `duration` 作为本次请求执行时间。

## 输出文件

运行结束后，结果会保存到：

```text
examples/07_trace_oracle/outputs/
```

实际生成：

```text
trace_oracle_sample.csv                # oracle 实际派出的样本（time, sample_id, duration, function_name, request_id, node_name, replica_id）
trace_input_summary.csv                # trace CSV 自身的摘要（每个函数的 sample_count / avg / min / max）
trace_sample_summary.csv               # 实际取样的摘要（每个函数的实际取样次数 / 取样后 avg/min/max duration）
trace_invoke_sample_join.csv           # 论文 demo 关键：每个 invoke 与其使用的 trace sample 一一对应 + duration_match
trace_cycle_summary.csv                # trace 循环覆盖证据（fast 16 调用 / 12 样本 → cycles_used=2, last_sample_id=4）
trace_invocation_summary.csv           # invocations.csv 按 function_name 聚合
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

## 关键导出与图

### 1. `trace_invoke_sample_join.csv` —— 调用 × 取样关联（README §5 核心）

按 `(function_name, invoke_order)` 一一对应：

- `sample_id`        oracle 派出的 trace 样本序号
- `sample_duration`  oracle 派出的执行时间（来自 trace CSV）
- `inv_t_start`      invocations.csv 中的执行起始 simtime
- `inv_t_exec`       invocations.csv 中的实际执行时长
- `duration_match`   `sample_duration == inv_t_exec`（完全相等为 True）

预期 28 行（16 fast + 12 slow），**`duration_match` 全部为 True** —— 这是 oracle 行为正确的最强证据。

### 2. `trace_cycle_summary.csv` —— trace 循环覆盖证据

| function_name | input_samples | actual_samples | cycles_used | full_cycles | last_sample_id |
|---|---|---|---|---|---|
| trace-fast-python-pi | 12 | 16 | 2 | 1 | 4 |
| trace-slow-python-pi | 12 | 12 | 1 | 1 | 12 |

`last_sample_id` 直接证明 fast 函数第二次循环用到第 4 个样本就停了（因为 12+4=16）。

### 3. 论文 demo 关键图 —— trace 取样序列与 invoke t_exec 对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/07_trace_oracle/outputs/trace_invoke_sample_join.csv")

fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
for ax, (fn, sub) in zip(axes, df.groupby("function_name")):
    ax.plot(sub["invoke_order"], sub["sample_duration"], "o-", label="trace sample_duration", color="steelblue")
    ax.plot(sub["invoke_order"], sub["inv_t_exec"], "x--", label="invocation t_exec", color="darkorange")
    ax.set_title(fn)
    ax.set_xlabel("invoke order")
    ax.set_ylabel("duration (simtime)")
    ax.legend()
    ax.grid(True, alpha=0.3)
plt.suptitle("Trace sample vs invocation t_exec (x 和 o 完全重合 = oracle 行为正确)")
plt.tight_layout()
plt.show()
```

### 4. trace 循环覆盖可视化

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/07_trace_oracle/outputs/trace_invoke_sample_join.csv")

fig, ax = plt.subplots(figsize=(9, 4))
for fn, sub in df.groupby("function_name"):
    ax.plot(sub["invoke_order"], sub["sample_id"], "o-", label=fn)
ax.set_xlabel("invoke order")
ax.set_ylabel("trace sample_id")
ax.set_title("Trace cursor cycling: fast wraps (12 → 1), slow stays in one cycle")
ax.axhline(12.5, color="grey", linestyle=":", alpha=0.5, label="trace length (12)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，6 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `trace_oracle_sample.csv` 行数 == 16+12 = 28 | `len(sample) == 28` |
| `invocations.csv` 行数 == 16+12 = 28 | `len(inv) == 28` |
| `trace_invoke_sample_join.csv` 行数 == 28 | `len(join) == 28` |
| `trace_invoke_sample_join.csv` 的 `duration_match` 全部为 True | `join.duration_match.all()` |
| `trace_cycle_summary.csv` 中 fast `actual_samples=16, cycles_used=2, last_sample_id=4` | 直接读 |
| 每个 function 的 invocations 数 == max_requests | `trace_invocation_summary: fast=16, slow=12` |

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
7. **轮询 `env.metrics.records` 直到所有 28 次 invoke 完成**（替代原 `env.timeout(2.0)` 硬等待，trace duration 变大时不会丢请求）；
8. 导出 trace 和调用结果指标。

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
TraceSample          # 单条 trace 样本数据类
TraceRuntimeOracle   # 按 function_name 维护 cursor，sample 时返回下一个样本，到末尾后循环
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
env.metrics.log("trace_oracle_sample", {"sample_id": ..., "duration": ...}, ...)
yield env.timeout(sample.duration)
```

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 8 个 faas-sim / oracle 原生 metric（`trace_oracle_sample` / `invocations` /
  `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `flow`）
- `trace_input_summary.csv`：trace CSV 自身摘要
- `trace_sample_summary.csv`：实际取样摘要
- `trace_invoke_sample_join.csv`：调用 × 取样关联
- `trace_cycle_summary.csv`：trace 循环覆盖证据
- `trace_invocation_summary.csv`：invocations.csv 按函数聚合

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。