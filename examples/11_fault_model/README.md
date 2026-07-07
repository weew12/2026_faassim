# 11_fault_model：faas-sim 故障模型样例

本样例用于演示如何在 faas-sim 中构造简单、可复现的故障模型。样例不修改 faas-sim 核心代码，而是在函数执行模拟器中引入故障判定逻辑，并通过自定义指标记录请求成败与故障原因。

## 运行方式

将 `fault_model/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/11_fault_model/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何定义节点不可用窗口；
2. 如何模拟函数副本瞬时失败；
3. 如何模拟网络退化导致的执行时间变长；
4. 如何将故障判定写入 `fault_model_probe.csv`；
5. 如何导出故障事件时间线；
6. **如何验证 probe 中的故障判定和故障窗口在 simtime 上严格对齐**（论文 demo 关键证据）；
7. **如何验证 simulator 派发的 final_duration 和 faas-sim 记录的 t_exec 完全一致**。

## 故障模型

样例内置三类故障：

```text
node_outage             节点不可用窗口，请求快速失败（failure_latency=0.03）
replica_error           周期性函数副本错误（每 7 个请求触发一次），请求快速失败
network_degradation     网络退化，请求仍成功但执行时间增加（base+0.45=0.70s）
```

故障事件表（fault_events.csv）：

| name | type | start | end | target_node | severity | extra_delay |
|---|---|---|---|---|---|---|
| node_outage_server_0 | node_outage | 1.00 | 1.80 | server_0 | hard | 0.0 |
| network_degradation_server_0 | network_degradation | 2.20 | 3.60 | server_0 | soft | 0.45 |

判定优先级（fault_model.decide）：
1. **node_outage 窗口内** → 失败，reason=node_outage
2. **request_id % 7 == 0**（replica_error_mod=7） → 失败，reason=replica_error
3. **network_degradation 窗口内** → 成功，reason=network_degradation，final_duration=base+extra_delay
4. 其他 → 成功，reason=normal

## 重要说明

faas-sim 默认 `invocations.csv` 只记录调用耗时，不直接表达 HTTP 状态码或业务成败。因此本样例将请求成败记录在自定义指标中：

```text
fault_model_probe.csv
```

分析请求是否失败时，应优先查看 `fault_model_probe.csv` 中的：

```text
success         bool
reason          node_outage / replica_error / network_degradation / normal
active_fault    fault event name that fired
final_duration  simulator 派发的执行时长（含故障放大）
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/11_fault_model/outputs/
```

实际生成：

```text
fault_model_probe.csv                # 每次请求的故障判定（30 行）
fault_timeline.csv                   # 故障事件开始/结束时间线
fault_events.csv                     # 故障事件表（从 fault_model.events_dataframe()）
fault_model_summary.csv              # 总体验成败摘要
fault_reason_distribution.csv        # 按 reason × success 分组的耗时分布
probe_with_simtime.csv               # 论文 demo 关键：probe + 重建 simtime 列
probe_fault_window_check.csv         # 论文 demo 关键：probe × fault_events 窗口命中验证（30/30 match）
probe_invocation_join.csv             # probe × invocations 关联，duration_match 验证
function_utilization.csv
node_utilization.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

> 旧 README 列出的 `resource.csv / resources.csv / resource_monitor.csv / resource_state.csv`
> 这 4 个 CSV 在 faas-sim 当前版本中不存在对应的 metric，已删除并替换为实际生成的
> `function_utilization.csv` / `node_utilization.csv`。

## 关键导出与图

### 1. `probe_fault_window_check.csv` —— 故障窗口命中验证（论文 demo 关键证据）

按 (function_name, replica_id, request_id) 给出每条 probe 的：
- `simtime`           重建后的 simtime（用 invocations 的 t_start 对齐）
- `in_window_faults`  该 simtime 时刻位于哪些故障窗口内（用 ; 连接）
- `expected_in_window` reason 期望是否在窗口内
- `window_match`      实际命中是否与 expected 一致

预期 30 行 **`window_match=True` 30/30 = 100%**。

### 2. `probe_invocation_join.csv` —— probe × invocations 关联

按 (function_name, replica_id, request_id) 一一对应：

- `probe_final_duration`  simulator 派发的 final_duration
- `inv_t_exec`            faas-sim 记录的实际执行时长
- `duration_match`         完全相等为 True

预期 30 行 **`duration_match=True` 全部 True**。

### 3. 论文 demo 关键图 —— 故障窗口 vs 实际请求成败

```python
import pandas as pd
import matplotlib.pyplot as plt

probe = pd.read_csv("examples/11_fault_model/outputs/probe_with_simtime.csv")
faults = pd.read_csv("examples/11_fault_model/outputs/fault_events.csv")

fig, ax = plt.subplots(figsize=(11, 4))
color_map = {
    "normal": "steelblue",
    "node_outage": "crimson",
    "replica_error": "darkorange",
    "network_degradation": "mediumseagreen",
}
for reason, sub in probe.groupby("reason"):
    ax.scatter(sub["simtime"], [reason] * len(sub),
               s=60, color=color_map.get(reason, "grey"), label=f"{reason} (n={len(sub)})")
for _, ev in faults.iterrows():
    ax.axvspan(ev["start_time"], ev["end_time"], alpha=0.15, color=color_map.get(ev["fault_type"], "lightgrey"))
ax.set_xlabel("simtime")
ax.set_title("Fault window vs probe reason (window match 30/30)")
ax.legend(loc="upper right")
plt.tight_layout()
plt.show()
```

### 4. 故障原因分布柱状图

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/11_fault_model/outputs/fault_reason_distribution.csv")
fig, ax = plt.subplots(figsize=(8, 4))
labels = [f"{r.reason}\n(success={r.success})" for r in df.itertuples()]
colors = ["crimson" if not r.success else "mediumseagreen" for r in df.itertuples()]
ax.bar(labels, df["request_count"], color=colors)
ax.set_ylabel("request count")
ax.set_title("Fault reason distribution (30 requests)")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，7 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `fault_model_probe.csv` 行数 == 30 | `len(probe) == 30` |
| `invocations.csv` 行数 == 30 | `len(inv) == 30` |
| `probe_fault_window_check.csv` 的 `window_match=True` 数 == 30 | `window_check.window_match.sum() == 30` |
| `probe_fault_window_check.csv` 中 `node_outage` 行的 `simtime` 都在 [1.0, 1.8] | 直接读 |
| `probe_fault_window_check.csv` 中 `network_degradation` 行的 `simtime` 都在 [2.2, 3.6] | 直接读 |
| `probe_invocation_join.csv` 的 `duration_match` 全部 True | `join.duration_match.all()` |
| `fault_reason_distribution.csv` 中 `node_outage`+`replica_error` 的 count 之和 == `failure_count` (7) | 4+3=7 ✓ |

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
8. **轮询 `env.metrics.records` 直到 30 次 invoke 全部完成**（替代原 `env.timeout(4)` 硬等待）；
9. 导出故障与调用结果指标；
10. log `window match = 100%` 和 `duration_match = True`。

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

并将判定结果写入 `fault_model_probe` 指标。

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把函数副本固定部署到目标节点 `server_0`，
使故障窗口稳定影响请求。

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 11 个 faas-sim / fault 原生 metric（`fault_model_probe` / `fault_timeline` /
  `invocations` / `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `flow` /
  `function_utilization` / `node_utilization`）
- `fault_events.csv`：故障事件表
- `fault_model_summary.csv`：总体成败摘要
- `fault_reason_distribution.csv`：按 reason × success 分组
- `probe_with_simtime.csv`：probe + 重建 simtime
- `probe_fault_window_check.csv`：probe × fault_events 窗口命中验证
- `probe_invocation_join.csv`：probe × invocations 关联

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。