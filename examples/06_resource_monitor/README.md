# 06_resource_monitor：faas-sim 原生 ResourceMonitor 资源监控样例

本样例用于演示 faas-sim 中 `ResourceState` 和 `ResourceMonitor` 的基本用法，重点展示函数执行期间如何登记 CPU / 内存资源占用、如何释放资源，以及如何把 ResourceMonitor 周期性采集到的资源利用率与函数调用按时间窗关联起来。

## 运行方式

将 `06_resource_monitor/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/06_resource_monitor/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 函数执行期间如何向 `env.resource_state` 登记 CPU / memory；
2. 函数执行结束后如何释放资源；
3. `ResourceMonitor` 如何周期性采集资源状态；
4. 如何从 `sim.env.metrics` 中导出资源监控 DataFrame；
5. **如何把 ResourceMonitor 周期性采集到的 cpu/mem util 和每次 invoke 的执行时间窗关联起来**，从而回答"这个调用实际拿到了多少资源"。

## 实验设计

样例部署一个函数：

```text
resource-heavy-python-pi
```

该函数保持 2 个副本，并触发 12 个请求。每次请求执行期间会登记：

```text
CPU      节点 CPU 容量的 35%（由 simulator.py 按 node.capacity.cpu_millis 动态计算）
Memory   128 MiB
执行时间  1.5 个仿真时间单位
```

请求结束后，CPU 和内存资源会从 `env.resource_state` 中释放。

> faas-sim 的 `ResourceMonitor(reconcile_interval=1)` 在 `sim.faassim.Simulation.run()` 中由
> `env.process(env.resource_monitor.run())` 启动，每 1 个 simtime 秒对所有 RUNNING 副本采样一次。
> 采样指标写入 `function_utilization`（per-replica：cpu / memory / cpu_util / mem_util）。

## 输出文件

运行结束后，结果会保存到：

```text
examples/06_resource_monitor/outputs/
```

实际生成：

```text
function_utilization.csv                # 06 关键：ResourceMonitor 周期性采集到的 per-replica 资源利用率
node_utilization.csv                    # 节点级资源利用率（本样例 UrbanSensing 拓扑下为 0 行，因 faas-sim ResourceMonitor 只在函数级采样）
invocations.csv                         # 每次 invoke 的 t_start/t_exec/replica 等
resource_utilization_per_replica.csv    # 06 新增：按 (node, replica_id) 聚合的 avg/max cpu+mem util
invocation_resource_join.csv            # 06 新增：每个 invoke 在 [t_start, t_start+t_exec] 内的 cpu/mem util
resource_monitor_summary.csv            # 总体资源监控摘要（采样数 / 监控副本数 / 平均峰值 util）
resource_monitor_invocation_summary.csv # 调用摘要（次数 / 函数数 / avg-max duration）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

> 旧版 README 列出的 `resource.csv / resources.csv / resource_monitor.csv / resource_state.csv`
> 这 4 个 CSV 在当前 faas-sim 版本中不存在（faas-sim 的 ResourceMonitor 实际记录的 metric 名是
> `function_utilization` / `node_utilization`），已从输出列表中删除。

## 关键导出与图

### 1. `resource_utilization_per_replica.csv` —— 每个副本的 CPU / 内存 util 画像

按 `(node, replica_id)` 聚合：

- `samples`              ResourceMonitor 在该副本上的采样次数
- `avg_cpu_util / max_cpu_util`   CPU 平均 / 峰值利用率（占节点 CPU 容量比）
- `avg_cpu_millis / max_cpu_millis` CPU 平均 / 峰值占用（毫核）
- `avg_mem_util / max_mem_util`   内存平均 / 峰值利用率
- `avg_mem_bytes / max_mem_bytes` 内存平均 / 峰值占用（字节）

```python
import pandas as pd
df = pd.read_csv("examples/06_resource_monitor/outputs/resource_utilization_per_replica.csv")
print(df[["node", "replica_id", "samples", "avg_cpu_util", "max_cpu_util", "avg_mem_util", "max_mem_util"]])
```

### 2. `invocation_resource_join.csv` —— 调用 × 资源关联（README §5 核心）

按 `(function_name, replica_id, t_start, t_exec)` 把 `invocations.csv` 的执行时间窗
和 `function_utilization.csv` 的 ResourceMonitor 采样按时间对齐。

- `samples_in_window`   该 invoke 在执行时间窗内被 ResourceMonitor 采到的次数
- `avg_cpu_util / max_cpu_util`   该 invoke 在窗口内的平均 / 峰值 CPU 利用率
- `avg_mem_util / max_mem_util`   该 invoke 在窗口内的平均 / 峰值内存利用率
- `avg_cpu_millis / max_cpu_millis`   该 invoke 在窗口内的平均 / 峰值 CPU 占用
- `avg_mem_bytes / max_mem_bytes`   该 invoke 在窗口内的平均 / 峰值内存占用

> 仿真时间窗重建说明：
> - `invocations.csv` 在 fields 中显式记录了 float simtime 的 `t_start` / `t_exec`，可直接读出。
> - `function_utilization.csv` 没有 simtime 字段（faas-sim 的 `extract_dataframe` 把
>   wall-clock datetime 当成 index）。但 ResourceMonitor 的采样间隔 `reconcile_interval`
>   已知（默认 1 simtime 秒），所以可以按 `replica_id` 内排序后用 `(rank + 1) * reconcile_interval`
>   重建 simtime。这一逻辑由 `analysis.build_invocation_resource_join` 实现。

**论文 demo 关键图**：每个 invoke 的 `avg_cpu_util` 柱状图（直观看 12 次 invoke 各自的资源画像）：

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/06_resource_monitor/outputs/invocation_resource_join.csv")
df["invocation_id"] = range(1, len(df) + 1)

fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(df["invocation_id"], df["avg_cpu_util"], color="steelblue", label="avg_cpu_util")
ax.bar(df["invocation_id"], df["max_cpu_util"], color="darkorange", alpha=0.6, label="max_cpu_util")
ax.set_xlabel("invocation id")
ax.set_ylabel("CPU utilization (fraction of node capacity)")
ax.set_title("Per-invocation CPU utilization (12 requests on 2 replicas, 0.35 each)")
ax.set_ylim(0, 1.0)
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

**为什么有些行 avg_cpu_util=0.525 而不是 0.7**：
两个副本轮流执行 invoke，所以某些 invoke 的执行窗口内**只有一个副本**正在跑（cpu_util=0.35），
另一个时刻**两个副本同时在跑**（各自 0.35，per-replica 看到 0.7）。窗口平均 ≈ 0.525。
这正是 README §5 想展示的"调用 × 资源"关联细节。

### 3. `resource_monitor_summary.csv` —— 总体资源摘要

```python
import pandas as pd
df = pd.read_csv("examples/06_resource_monitor/outputs/resource_monitor_summary.csv")
print(df.to_string(index=False))
```

预期输出（每次 ID 不同）：

```text
 total_resource_samples  monitored_replicas  monitored_nodes  overall_avg_cpu_util  overall_max_cpu_util  ...
                    13                   2                1              0.430769                   0.7  ...
```

## 数据自洽验证

跑完 `main.py` 后，6 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `function_utilization.csv` 行数 == 资源监控 summary 中的 `total_resource_samples` | `len(pd.read_csv("function_utilization.csv")) == resource_monitor_summary.total_resource_samples` |
| `invocations.csv` 行数 == 12（max_requests） | `len(pd.read_csv("invocations.csv")) == 12` |
| `invocation_resource_join.csv` 行数 == `invocations.csv` 行数 | `len(join) == len(inv)` |
| 每行 join 的 `samples_in_window` ≥ 1 | `(join.samples_in_window >= 1).all()` |
| `resource_utilization_per_replica.csv` 每行 `samples` 之和 == `function_utilization.csv` 行数 | `per_replica.samples.sum() == len(util)` |
| `monitored_replicas` == 2 | `summary.monitored_replicas == 2` |

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造函数部署；
5. 运行请求负载；
6. 导出资源监控和调用结果指标。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
ResourceMonitorSimulatorFactory
ResourceMonitorFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
env.resource_state.put_resource(replica, "cpu", cpu_millis)
env.resource_state.put_resource(replica, "memory", memory_bytes)
env.resource_state.remove_resource(replica, "cpu", cpu_millis)
env.resource_state.remove_resource(replica, "memory", memory_bytes)
```

从而让 ResourceMonitor 能够采集到资源使用变化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 7 个 faas-sim 原生 metric（`function_utilization` / `node_utilization` / `invocations` /
  `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `flow`）
- `resource_utilization_per_replica.csv`：per-replica CPU/mem util 聚合
- `invocation_resource_join.csv`：调用 × 资源 join
- `resource_monitor_summary.csv`：总体资源摘要
- `resource_monitor_invocation_summary.csv`：调用摘要

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。