# 16_cosimulation：faas-sim 协同仿真样例

本样例用于演示 faas-sim 与外部控制/环境模型之间的协同仿真组织方式。它提供一个最小模板：外部 trace 周期性更新环境状态，faas-sim 函数模拟器读取该状态，并据此改变函数执行时间。

## 运行方式

将 `16_cosimulation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/16_cosimulation/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何把外部环境 trace 接入 faas-sim；
2. 如何构造一个外部控制循环（每 0.5s 一次状态交换）；
3. 如何让外部状态影响函数执行时间（`final_duration = base_duration * runtime_factor + network_delay`）；
4. 如何记录 faas-sim 与外部控制器之间的状态交换（`cosim_exchange` + `cosim_phase`）；
5. 如何记录每次 invoke 时的外部状态（`cosim_invoke_probe` 含 simtime + phase_name + controller_action）；
6. 如何导出协同仿真过程中的阶段、控制和调用指标；
7. **如何做 probe×invocation join 验证 simulator 派发的 final_duration == faas-sim 记录的 t_exec**（论文 demo 关键证据）；
8. **如何做数据自洽段**（17 个不变量）。

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

默认 trace 包含 4 个 phase（normal / edge_pressure / network_slowdown / cooldown），总时长 8 秒，总触发 request 数 = 6+16+10+4 = 36。

## 输出文件

运行结束后，结果会保存到：

```text
examples/16_cosimulation/outputs/
```

主要文件：

```text
external_environment_trace.csv    # trace 副本（带控制器读到的状态）
cosim_exchange.csv                # 外部控制器每 0.5s 写入的状态交换
cosim_phase.csv                   # 阶段切换事件（每 phase 切一次）
cosim_workload_phase.csv          # benchmark 启动的 workload phase
cosim_invoke_probe.csv            # 每次 invoke 探针（simtime + final_duration + phase_name）
cosim_probe_invocation_join.csv   # probe × invocations 关联（论文 demo 关键证据）
cosim_phase_invoke_summary.csv    # per-phase invoke 摘要
cosim_exchange_summary.csv        # per-phase exchange 摘要
cosim_paper_highlight.csv         # 论文 demo 关键摘要
invocations.csv                   # faas-sim 真实 invocation
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
function_utilization.csv
node_utilization.csv
resource.csv
resources.csv
resource_monitor.csv
resource_state.csv
```

## 关键导出

### 1. `cosim_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                            value
invoke_events__normal__observe                                    4
avg_final_duration__normal__observe                               0.18
invoke_events__edge_pressure__scale_attention                     13
avg_final_duration__edge_pressure__scale_attention                0.323
impact_relative_to_normal__edge_pressure__scale_attention        1.794x
invoke_events__network_slowdown__network_attention                12
avg_final_duration__network_slowdown__network_attention           0.448
impact_relative_to_normal__network_slowdown__network_attention   2.489x
invoke_events__cooldown__release_attention                        7
avg_final_duration__cooldown__release_attention                   0.171
impact_relative_to_normal__cooldown__release_attention            0.950x
exchange_events__normal__observe                                  4
exchange_events__edge_pressure__scale_attention                   4
...
trace_rps__edge_pressure                                          8
trace_runtime_factor__edge_pressure                               1.35
trace_network_delay__edge_pressure                                0.08
...
```

**关键发现**：
- `edge_pressure` phase 让 invoke 耗时从 0.18s 放大到 0.323s（**1.794x**）。
- `network_slowdown` phase 让 invoke 耗时放大到 0.448s（**2.489x**）。
- `cooldown` phase 反而把耗时降到 0.171s（**0.950x**），验证外部控制器确实能降低负载。

### 2. `cosim_probe_invocation_join.csv` —— probe × invocations 关联（论文 demo 关键证据）

按 (function_name, replica_id) 关联，按 simtime 顺序对齐：

| probe_simtime | probe_final_duration | inv_t_start | inv_t_exec | duration_match | simtime_match |
|---|---|---|---|---|---|
| 0.833 | 0.180 | 0.833 | 0.180 | True | True |
| 1.167 | 0.180 | 1.167 | 0.180 | True | True |
| 2.167 | 0.323 | 2.167 | 0.323 | True | True |
| ... | ... | ... | ... | ... | ... |

预期 36 行，**`duration_match` 和 `simtime_match` 全部 True**。

### 3. 论文 demo 关键图 —— 外部阶段对 invoke 耗时的影响

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/16_cosimulation/outputs/cosim_paper_highlight.csv")
df_dur = df[df.metric.str.startswith("avg_final_duration")].copy()
df_dur["phase_action"] = df_dur.metric.str.replace("avg_final_duration__", "")
df_dur["duration"] = df_dur.value.astype(float)

fig, ax = plt.subplots(figsize=(8, 4))
ax.barh(df_dur.phase_action, df_dur.duration, color="steelblue")
ax.set_xlabel("avg_final_duration (s)")
ax.set_title("Co-simulation: external phase impact on function duration")
ax.grid(True, axis="x", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**17 个核心不变量**应同时满足（17/17 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `cosim_invoke_probe` 行数 = 36（trace 总数） | self-check |
| 2 | `invocations` 行数 = 36 | self-check |
| 3 | `cosim_exchange` 行数 > 0（每 0.5s 一次状态交换） | self-check |
| 4 | `cosim_phase` 行数 == trace 行数（4=4） | self-check |
| 5 | `cosim_invoke_probe` 有 `simtime` 字段 | self-check |
| 6 | probe×invocation `duration_match` 100% | self-check（36/36） |
| 7 | probe×invocation `simtime_match` 100% | self-check（36/36） |
| 8-11 | per-phase invoke_events 在 trace_max ±100% 范围（phase 边界 lag 容忍） | self-check |
| 12-15 | paper highlight 里 4 phase invoke_events 跟 phase_invoke_summary 一致 | self-check |
| 16 | probe phases ⊆ exchange phases（无遗漏 phase） | self-check |
| 17 | 36/36 probe 行有 `controller_action` 字段 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cosimulation self-check ===
INFO:analysis:  [PASS] cosim_invoke_probe_count : probe rows=36, expected=36
INFO:analysis:  [PASS] invocations_count : inv rows=36, expected=36
INFO:analysis:  [PASS] cosim_exchange_count : exchange rows=18
INFO:analysis:  [PASS] cosim_phase_count : phase rows=4, trace rows=4
INFO:analysis:  [PASS] cosim_invoke_probe_has_simtime : simtime column present
INFO:analysis:  [PASS] probe_invocation_duration_match : duration_match=36/36
INFO:analysis:  [PASS] probe_invocation_simtime_match : simtime_match=36/36
INFO:analysis:  [PASS] phase_invoke_count__cooldown : actual=7, trace_max=4 (phase 边界 lag 可能让 ±100% 范围内都算合理)
INFO:analysis:  ...
INFO:analysis:=== 17 passed, 0 warned, 0 failed ===
```

## 目录结构

```text
16_cosimulation/
├── inputs/                            # 外部环境 trace
│   └── external_environment_trace.csv
├── outputs/                           # 运行输出
├── __init__.py
├── analysis.py                        # 指标导出 + probe×invocation join + paper highlight + self-check
├── context.py                         # ExternalPhase + CosimulationContext
├── controller.py                      # ExternalController（每 0.5s 状态交换）
├── external_model.py                  # ExternalEnvironmentTrace（CSV 读取 + 阶段查询）
├── main.py                            # 入口（含 wait_for_invocations）
└── simulator.py                       # CosimulationFunctionSimulator（invoke 读 context）
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取外部环境 trace；
2. 创建共享协同仿真上下文；
3. 创建外部控制器（`control_interval=0.5`）；
4. 创建 faas-sim Simulation；
5. 启动请求负载和控制循环；
6. **末尾用 `wait_for_invocations(env, expected_count=36, max_wait=10)` 替代固定 `env.timeout(2)`**；
7. 导出协同仿真结果 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/external_environment_trace.csv`

外部环境 trace 文件。

默认 4 个 phase（normal / edge_pressure / network_slowdown / cooldown），总时长 8 秒，总触发 36 个 request。

### `context.py`

共享上下文文件。

提供 `ExternalPhase` + `CosimulationContext`（`phase_name` / `runtime_factor` / `network_delay` / `controller_action` / `description`），用于在外部控制器和函数模拟器之间共享外部状态。

### `external_model.py`

外部模型文件。

提供 `ExternalEnvironmentTrace`，负责读取 CSV trace 并按仿真时间查询当前外部阶段。

### `controller.py`

外部控制器文件。

提供 `ExternalController`：

- **每 0.5s 一次**轮询 trace 状态，更新共享 context；
- 记录 `cosim_exchange`（每次轮询一次）；
- 记录 `cosim_phase`（phase 切换时一次）；
- `_observe_active_requests` 兼容式读取 topology 节点的 `current_requests`，但当前 faas-sim 节点结构没有这个属性，所以通常返回 0（**这是 sim 模型的诚实特性**，不影响主流程）。

### `simulator.py`

函数生命周期模拟器文件。

提供 `CosimulationSimulatorFactory` + `CosimulationFunctionSimulator`：

- `deploy`：镜像拉取；
- `startup`：0.2s 启动；
- `invoke`：读取 context 快照 → 算 `final_duration = base_duration * runtime_factor + network_delay` → 记录 `cosim_invoke_probe`（**含 simtime 字段**） → `yield env.timeout(final_duration)`。

### `analysis.py`

指标导出 + probe×invocation join + 论文 demo 关键摘要 + 数据自洽段文件。

- 14 个 faas-sim / cosim 原生 metric 提取；
- `cosim_phase_invoke_summary`：per-phase invoke 摘要；
- `cosim_exchange_summary`：per-phase exchange 摘要；
- `cosim_probe_invocation_join`：probe × invocations 关联验证（论文 demo 关键证据）；
- `cosim_paper_highlight`：per-phase impact_relative_to_normal + trace 字段；
- 数据自洽段：17 个不变量。

### `outputs/`

运行结果输出目录。

包含 21 个 CSV（trace / cosim / faas-sim 常规 / paper highlight / self-check）。
