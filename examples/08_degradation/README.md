# 08_degradation：faas-sim 性能退化样例

本样例用于演示函数执行过程中的性能退化建模。核心思想是：当同一节点上已有请求正在执行时，新到达请求会受到资源竞争影响，其执行时间被放大。

## 运行方式

将 `degradation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/08_degradation/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何利用 `node.current_requests` 观察节点当前并发负载；
2. 多个请求共节点执行时如何构造性能退化；
3. 如何将基础执行时间放大为退化后的执行时间；
4. 如何记录每次请求的退化因子；
5. **如何验证 simulator 派发的 final_duration 就是 faas-sim 记录的实际执行时间**（论文 demo 关键证据）。

## 退化模型

样例使用线性节点竞争退化模型：

```text
final_duration = base_duration * (1 + alpha * max(active_requests_before, 0))
```

其中：

```text
base_duration           无竞争时的基础执行时间（默认 0.4 simtime 秒）
active_requests_before  本请求加入 node.current_requests 之前节点上已有的并发请求数
alpha                   每个并发请求带来的执行时间放大系数（默认 0.35）
final_duration          退化后的本次请求执行时间
```

> **关键设计点**：`active_requests_before` 在 `node.current_requests.add(request)` **之前** 读取，
> 表示"该请求到达时节点上已有多少请求在跑"，不是"包含自己"。

## 实验设计

样例部署一个函数：

```text
degradation-python-pi
```

配置：

```text
scale_min = 3          # 3 个副本
scale_max = 3
请求速率 rps = 18       # 触发请求重叠
max_requests = 40      # 总请求数
```

同时使用 `FixedNodeScheduler` 把 3 个副本**强制部署到同一节点 `server_0`**，
加上 18 rps 的高并发率，会产生大量 in-flight 请求（`active_requests_before` 最大可达 29），
从而稳定展示性能退化现象。

## 输出文件

运行结束后，结果会保存到：

```text
examples/08_degradation/outputs/
```

实际生成：

```text
degradation_probe.csv                   # 每次请求的退化采样（active_requests_before / degradation_factor / final_duration）
degradation_summary.csv                 # 按 (function_name, node_name) 聚合的退化摘要
degradation_concurrency_distribution.csv # 按 active_requests_before 分组的执行时间分布（论文 demo 关键图）
degradation_invoke_join.csv             # 论文 demo 关键：probe × invocations 关联，duration_match 全部 True
degradation_model_consistency.csv       # 退化公式一致性：max_abs_diff == 0
invocations.csv                         # faas-sim 原生调用记录（40 行）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
function_utilization.csv                # ResourceMonitor 周期性采集（默认 reconcile_interval=1）
node_utilization.csv                    # 节点级（本样例 UrbanSensing 拓扑下为 0 行）
```

> 旧 README 列出的 `resource.csv / resources.csv / resource_monitor.csv / resource_state.csv`
> 这 4 个 CSV 在 faas-sim 当前版本中并不存在对应的 metric，
> 已删除并替换为实际生成的 `function_utilization.csv` / `node_utilization.csv`。

## 关键导出与图

### 1. `degradation_model_consistency.csv` —— 退化公式数学一致性

```text
probe_count=40  base_duration=0.4  alpha=0.35  max_abs_diff=0.0  pass_tolerance=True
```

`max_abs_diff == 0` 证明 simulator 实现的退化公式和 model 的声明完全一致。

### 2. `degradation_invoke_join.csv` —— probe × invocations 关联（论文 demo 关键证据）

按 (function_name, request_id) 把 `degradation_probe` 和 `invocations` 一一对应：

- `probe_final_duration`  simulator 派发的最终执行时间
- `inv_t_exec`            faas-sim 记录的实际执行时间
- `duration_match`         两个值是否完全相等

预期 40 行，**`duration_match` 全部 True**。

### 3. 论文 demo 关键图 —— 并发数 vs 执行时间

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/08_degradation/outputs/degradation_concurrency_distribution.csv")
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.plot(df["active_requests_before"], df["avg_final_duration"], "o-", color="steelblue",
        label="avg final_duration")
ax.plot(df["active_requests_before"], df["max_final_duration"], "s--", color="darkorange",
        label="max final_duration")
# 理论曲线：final = 0.4 * (1 + 0.35 * active)
xs = df["active_requests_before"].values
ax.plot(xs, 0.4 * (1 + 0.35 * xs), ":", color="grey", alpha=0.7,
        label="theory: 0.4 × (1 + 0.35 × active)")
ax.set_xlabel("active_requests_before")
ax.set_ylabel("final_duration (simtime)")
ax.set_title("Degradation: request execution time vs node concurrent load")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
```

### 4. 退化分布柱状图

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/08_degradation/outputs/degradation_concurrency_distribution.csv")
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(df["active_requests_before"], df["request_count"], color="steelblue")
ax.set_xlabel("active_requests_before")
ax.set_ylabel("request count")
ax.set_title("How often each concurrency level was hit during the run")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，7 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `degradation_probe.csv` 行数 == 40 (max_requests) | `len(probe) == 40` |
| `invocations.csv` 行数 == 40 | `len(inv) == 40` |
| `degradation_invoke_join.csv` 行数 == 40 | `len(join) == 40` |
| `degradation_invoke_join.csv` 的 `duration_match` 全部 True | `join.duration_match.all()` |
| `degradation_model_consistency.csv` 的 `max_abs_diff == 0` | `cons.max_abs_diff.iloc[0] < 1e-9` |
| `degradation_concurrency_distribution.csv` 中 active=0 行的 `avg_final_duration == 0.4` | base_duration |
| `degradation_concurrency_distribution.csv` 中 active=29 行的 `avg_final_duration == 4.46` | 0.4 × (1 + 0.35 × 29) |

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造 3 副本函数部署；
5. 使用固定节点调度器制造共节点并发；
6. 运行请求负载；
7. **轮询 `env.metrics.records` 直到所有 40 次 invoke 完成**（替代原 `env.timeout(3)` 硬等待，
   并发峰值时 final_duration 可达 4.46s，硬等待必丢请求）；
8. 导出退化和调用结果指标。

### `degradation_model.py`

性能退化模型文件。

该文件提供：

```text
LinearNodeContentionDegradationModel
DegradationSample
```

用于根据节点已有并发请求数计算退化后的执行时间。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
DegradationSimulatorFactory
DegradationFunctionSimulator
```

其核心逻辑是在 `invoke()` 中读取：

```text
active_requests_before = len(node.current_requests)   # 加入 current_requests 之前
sample = self.model.sample(active_requests_before)
env.metrics.log("degradation_probe", ...)
node.current_requests.add(request)
yield env.timeout(sample.final_duration)
```

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把多个函数副本固定部署到同一节点 `server_0`，
从而稳定触发共节点并发退化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 10 个 faas-sim / probe 原生 metric（`degradation_probe` / `invocations` /
  `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `flow` /
  `function_utilization` / `node_utilization`）
- `degradation_summary.csv`：按 (function_name, node_name) 聚合的退化摘要
- `degradation_concurrency_distribution.csv`：按 active_requests_before 分组的执行时间分布
- `degradation_invoke_join.csv`：probe × invocations 关联
- `degradation_model_consistency.csv`：退化公式一致性

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。