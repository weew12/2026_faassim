# 12_cold_start：faas-sim 冷启动生命周期拆分样例

本样例用于演示 faas-sim 中函数副本冷启动路径的拆分建模方法，重点展示 `deploy`、`startup`、`setup`、`first_invoke` 和 `warm_invoke` 的区别。

## 运行方式

将 `cold_start/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/12_cold_start/main.py
```

## 样例目标

该样例主要回答以下问题：

1. faas-sim 中函数副本启动过程如何经过 deploy、startup 和 setup；
2. `docker.pull()` 如何作为 deploy 阶段的一部分影响冷启动路径；
3. 如何区分首次请求 `first_invoke` 和热路径请求 `warm_invoke`；
4. 如何记录每个阶段的开始时间、结束时间和阶段耗时；
5. 如何生成副本级冷启动路径摘要；
6. **如何验证 simulator 派发的 invoke 时长和 faas-sim 记录的 t_exec 完全一致**（论文 demo 关键证据）。

## 阶段定义

样例将函数启动和调用过程拆成五类事件：

```text
deploy        镜像拉取或部署准备阶段（含 docker.pull）
startup       容器/运行时启动阶段（默认 0.75s）
setup         函数业务初始化阶段（默认 0.55s）
first_invoke  副本首次请求执行阶段（默认 0.30s）
warm_invoke   副本后续热路径请求执行阶段（默认 0.08s）
```

其中冷启动激活路径定义为：

```text
cold_activation_duration = deploy + startup + setup
```

首次请求路径定义为：

```text
first_request_path_duration = deploy + startup + setup + first_invoke
```

本样例的默认参数让冷启动关键事实非常清晰：
- cold_activation ≈ 0.80 + 0.75 + 0.55 = **2.10s**
- first_request_path ≈ 2.10 + 0.30 = **2.40s**
- 后续 warm_invoke 只需 **0.08s** —— **first/warm = 3.75x**

## 重要说明

faas-sim 默认流程是在函数部署阶段创建并启动副本，请求到达时通常已经存在 RUNNING 副本。因此本样例重点刻画"副本从创建到可用"的冷启动路径，而不是 OpenFaaS 网关 scale-from-zero 场景下的请求阻塞等待过程。

后续如果要研究 scale-from-zero，可以在此基础上增加自定义 FaaSSystem 或控制器逻辑，使请求到达时触发副本创建并统计请求等待时间。

## 输出文件

运行结束后，结果会保存到：

```text
examples/12_cold_start/outputs/
```

实际生成：

```text
cold_start_probe.csv                  # 每次阶段的 phase_start / phase_finish / phase_duration（6 行）
cold_start_phase_summary.csv          # 按 phase 分组的 events/avg/min/max duration
cold_start_replica_path_summary.csv   # 按 replica 汇总：cold_activation_duration / first_request_path_duration
cold_start_warm_cold_compare.csv      # first_invoke vs warm_invoke 的对比（论文 demo 关键）
cold_start_probe_invocation_join.csv  # 论文 demo 关键：probe × invocations 关联，duration_match 全部 True
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

### 1. `cold_start_warm_cold_compare.csv` —— first vs warm 对比

```text
       phase  request_events  avg_invoke_duration
first_invoke               1                 0.30
 warm_invoke               2                 0.08
```

**论文 demo 关键数字**：first/warm = 0.30/0.08 = **3.75x speedup**。
这是冷启动感知调度 / 预热策略的核心论点。

### 2. `cold_start_replica_path_summary.csv` —— 单副本冷启动路径

```text
replica_id  function_name        node_name  deploy_total  startup_total  setup_total  first_invoke_total  warm_invoke_total  cold_activation  first_request_path
<id>        cold-start-python-pi server_0               0.80           0.75         0.55                  0.30                0.16             2.10              2.40
```

- `cold_activation = 0.80 + 0.75 + 0.55 = 2.10s`（deploy/startup/setup 累计）
- `first_request_path = cold_activation + first_invoke = 2.40s`

### 3. `cold_start_probe_invocation_join.csv` —— probe × invocations 关联（论文 demo 关键证据）

```text
replica_id  phase          probe_phase_duration  inv_t_exec  duration_match
<id>        first_invoke                  0.30        0.30            True
<id>        warm_invoke                   0.08        0.08            True
<id>        warm_invoke                   0.08        0.08            True
```

3 行全部 `duration_match=True` —— simulator 派发的执行时长和 faas-sim 记录的实际执行时长完全一致。

### 4. 论文 demo 关键图 —— 冷启动路径阶段分解

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/12_cold_start/outputs/cold_start_replica_path_summary.csv")
row = df.iloc[0]

phases = ["deploy", "startup", "setup", "first_invoke", "warm_invoke_avg"]
durations = [
    row["deploy_total_duration"],
    row["startup_total_duration"],
    row["setup_total_duration"],
    row["first_invoke_total_duration"],
    row["warm_invoke_total_duration"] / row["warm_invoke_events"],
]
colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

fig, ax = plt.subplots(figsize=(9, 4))
bars = ax.bar(phases, durations, color=colors)
for bar, val in zip(bars, durations):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
            f"{val:.2f}s", ha="center")
ax.set_ylabel("duration (simtime)")
ax.set_title("Cold start path: deploy + startup + setup + first_invoke = 2.4s vs warm 0.08s")
plt.tight_layout()
plt.show()
```

### 5. first vs warm 直接对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/12_cold_start/outputs/cold_start_warm_cold_compare.csv")
fig, ax = plt.subplots(figsize=(6, 4))
bars = ax.bar(df["phase"], df["avg_invoke_duration"],
              color=["crimson", "steelblue"])
for bar, val in zip(bars, df["avg_invoke_duration"]):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
            f"{val:.2f}s", ha="center")
ax.set_ylabel("duration (simtime)")
ax.set_title(f"first_invoke 0.30s vs warm_invoke 0.08s — 3.75x speedup")
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，7 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `cold_start_probe.csv` 至少包含 deploy / startup / setup / first_invoke / warm_invoke 5 个 phase | `probe.phase.value_counts()` |
| `invocations.csv` 行数 == 3 (max_requests) | `len(inv) == 3` |
| `first_invoke_avg == 0.30, warm_invoke_avg == 0.08` | warm_cold_compare |
| `cold_activation_duration ≈ 2.10`（0.80 + 0.75 + 0.55） | replica_path_summary |
| `first_request_path_duration ≈ 2.40`（cold_activation + 0.30） | replica_path_summary |
| `cold_start_probe_invocation_join.csv` 的 `duration_match` 全部 True | `join.duration_match.all()` |
| `cold_start_phase_summary.csv` 中 first_invoke 和 warm_invoke 的 events 之和 == invocations 行数 | 1 + 2 = 3 ✓ |

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造函数部署；
5. 运行三次请求（first_invoke + 2× warm_invoke）；
6. **轮询 `env.metrics.records` 直到 3 次 invoke 全部完成**（替代原 `env.timeout(2)` 硬等待）；
7. 导出冷启动阶段和调用结果指标；
8. log `probe × invocation join` 一致性。

### `cold_start_model.py`

冷启动阶段模型文件。

该文件提供：

```text
ColdStartPhaseConfig
ColdStartModel
```

用于配置 startup、setup、first_invoke 和 warm_invoke 的确定性耗时。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
ColdStartSimulatorFactory
ColdStartFunctionSimulator
```

其核心逻辑是在 `deploy()` / `startup()` / `setup()` / `invoke()` 中分别记录 `cold_start_probe` 指标，
invoke 阶段通过 `first_invoke_seen[replica_key]` 区分 first/warm。

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 10 个 faas-sim / cold_start 原生 metric（`cold_start_probe` / `invocations` /
  `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `flow` /
  `function_utilization` / `node_utilization`）
- `cold_start_phase_summary.csv`：阶段耗时摘要
- `cold_start_replica_path_summary.csv`：副本冷启动路径
- `cold_start_warm_cold_compare.csv`：first vs warm 对比
- `cold_start_probe_invocation_join.csv`：probe × invocations 关联验证

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。