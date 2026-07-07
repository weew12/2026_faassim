# 10_data_locality：faas-sim 数据本地性样例

本样例用于演示 faas-sim / Skippy 中的数据本地性机制，重点展示 `StorageIndex`、函数数据标签、`DataLocalityPriority` 和 `simulate_data_download()` 之间的关系。

## 运行方式

将 `data_locality/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/10_data_locality/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何使用 `StorageIndex` 登记对象数据所在节点；
2. 函数如何通过标签声明需要读取哪个对象；
3. Skippy 默认 `DataLocalityPriority` 如何影响节点选择；
4. `simulate_data_download()` 如何根据数据位置触发网络传输；
5. 数据本地性感知调度和强制远端调度在下载耗时上的差异。

## 实验设计

样例构造一个小型边缘-存储拓扑：

```text
edge_near   靠近 storage_near，带宽高、延迟低（near_link=200 Mbps, latency=3ms）
edge_mid    中等距离            （mid_link=60 Mbps, latency=10ms）
edge_far    远离 storage_near，带宽低、延迟高（far_link=10 Mbps, latency=30ms）
storage_near  保存输入对象的存储节点（storage_link=200 Mbps, latency=2ms）
```

输入对象为：

```text
video-bucket/frame-seq-001   size=64M   位于 storage_near
```

函数通过以下标签声明输入数据：

```text
data.skippy.io/receives-from-storage=64M
data.skippy.io/receives-from-storage/path=video-bucket/frame-seq-001
```

样例运行两个场景：

```text
data_locality_aware   使用 Skippy 默认数据本地性优先级 → 倾向选择 edge_near
forced_remote         强制调度到 edge_far，作为远端访问对比组
```

> **本样例不触发 invoke**：Benchmark 只调用 `poll_available_replica`，关注的是**数据下载阶段**的耗时差异，
> 不涉及函数执行业务。`invocations.csv` 永远是 0 行（符合设计）。

## 输出文件

运行结束后，结果会保存到：

```text
examples/10_data_locality/outputs/
```

每个场景有独立子目录：

```text
outputs/data_locality_aware/        # 数据本地性感知场景
outputs/forced_remote/              # 强制远端调度对比场景
```

每个子目录：

```text
data_locality_scheduler_result.csv  # 调度器记录：feasible_nodes / needed_images / selected_node
data_locality_candidate.csv         # 每个候选节点的估算下载时间 + 带宽（仅 data_locality_aware）
data_locality_download.csv          # 实际下载时长（每个 replica 一条）
candidate_vs_actual_join.csv        # 论文 demo 关键：candidate 估算 vs download 实际，按 candidate_node 对齐
data_locality_summary.csv           # 单场景摘要（含 theoretical_download_duration 反算）
flow.csv                            # 网络流（action_type=docker_pull / data_download）
network.csv                         # 链路级传输记录（link_name / type / bytes）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv                     # 设计上为 0 行
```

跨场景对比文件（在 `outputs/` 顶层）：

```text
data_locality_comparison.csv        # 两场景 side-by-side
data_locality_paper_highlight.csv   # 论文 demo 关键摘要：aware/forced 下载时长 + 20x speedup
```

## 关键导出与图

### 1. `data_locality_paper_highlight.csv` —— 论文 demo 核心

```text
metric                              value
aware_download_seconds              2.654
forced_download_seconds             52.880
speedup_ratio_forced_over_aware     19.9
aware_theoretical_seconds           2.441
forced_theoretical_seconds          48.828
```

**关键发现**：把函数调度到 `edge_far` 比调度到 `edge_near` 数据下载耗时 **慢 19.9 倍**。

### 2. `candidate_vs_actual_join.csv` —— Skippy 估算 vs 实际下载（论文 demo 关键证据）

`data_locality_aware` 场景下，按 candidate_node 对齐后：

```text
candidate_node  estimated_download_time  best_bandwidth_mbps  actual_download_duration  estimated_vs_actual_diff  match_tolerance_5pct
edge_near                          2.56                  200                  2.654                   0.094                   True
edge_mid                           8.53                   60                    NaN                        —                     —
edge_far                          51.20                   10                    NaN                        —                     —
```

`edge_near` 行的 `match_tolerance_5pct=True` 说明 Skippy `DataLocalityPriority` 估算的下载时间和 `simulate_data_download()` 实际跑出来的下载时间误差 < 5%。

### 3. 论文 demo 关键图 —— aware vs forced 下载时长

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/10_data_locality/outputs/data_locality_comparison.csv")
hl = pd.read_csv("examples/10_data_locality/outputs/data_locality_paper_highlight.csv")
speedup = float(hl[hl.metric == "speedup_ratio_forced_over_aware"]["value"].iloc[0])

fig, ax = plt.subplots(figsize=(7, 4))
bars = ax.bar(df["scenario"], df["total_download_duration"], color=["steelblue", "darkorange"])
for bar, val in zip(bars, df["total_download_duration"]):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
            f"{val:.2f}s", ha="center")
ax.set_ylabel("data download duration (simtime)")
ax.set_title(f"Data locality awareness: forced_remote is {speedup:.1f}x slower")
plt.tight_layout()
plt.show()
```

### 4. 候选节点估算下载时间分布

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/10_data_locality/outputs/data_locality_aware/candidate_vs_actual_join.csv")
fig, ax = plt.subplots(figsize=(7, 4))
bars = ax.bar(df["candidate_node"], df["estimated_download_time"], color="steelblue")
for bar, val in zip(bars, df["estimated_download_time"]):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
            f"{val:.2f}s", ha="center")
ax.set_ylabel("estimated download time (simtime)")
ax.set_title("DataLocalityPriority estimates per candidate node")
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，6 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `data_locality_paper_highlight.csv` 中 `speedup_ratio_forced_over_aware` ≥ 10 | forced/aware 数据下载时长差距 |
| `data_locality_aware/candidate_vs_actual_join.csv` 中 `edge_near` 行 `match_tolerance_5pct=True` | Skippy 估算 vs 实际 ≤ 5% |
| `data_locality_comparison.csv` 中 `aware.selected_node == 'edge_near'` | Skippy 默认调度选最近节点 |
| `data_locality_comparison.csv` 中 `forced.selected_node == 'edge_far'` | ForcedNodeScheduler 工作正确 |
| `data_locality_aware/data_locality_summary.csv` 中 `theoretical_vs_actual_diff` < 1.0s | 理论带宽反算 vs 实际下载 |
| `invocations.csv` 行为 0 行 | 样例不触发 invoke 是设计选择 |

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建数据本地性拓扑；
2. 创建 StorageIndex；
3. 注册函数镜像；
4. 构造带数据标签的函数部署；
5. 分别运行数据本地性感知调度和强制远端调度；
6. 导出结果并生成对比摘要；
7. log 论文 demo 关键摘要（`speedup = forced / aware`）。

### `topology.py`

拓扑构建文件。

该文件创建 `edge_near`、`edge_mid`、`edge_far` 和 `storage_near`，并设置不同带宽和延迟，用于稳定制造近数据节点与远数据节点的差异。

### `storage.py`

对象存储索引文件。

该文件提供：

```text
DEFAULT_DATA_OBJECT
build_storage_index()
```

用于登记 `video-bucket/frame-seq-001` 位于 `storage_near`。

### `scheduler.py`

调度器文件。

该文件提供：

```text
InstrumentedDataLocalityScheduler
ForcedNodeScheduler
```

前者保留 Skippy 默认调度语义并记录候选节点数据本地性信息（`estimated_download_time`、`best_bandwidth_mbps`），
后者用于构造强制远端对比组。

> **修复说明**：`InstrumentedDataLocalityScheduler._log_data_locality_candidates` 中
> `best_bandwidth` 来自 `cluster_context.get_dl_bandwidth()`，单位是 Mbps（与 `Link(bandwidth=200, ...)` 一致）。
> `estimated_download_time` 计算时需要先把 Mbps 转成 bytes/s：`bandwidth_mbps * 1.25e5`。
> 之前直接 `data_item.size / best_bandwidth` 是单位错配，会让估算时间多 4 个数量级。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
DataLocalitySimulatorFactory
DataLocalityFunctionSimulator
```

其核心逻辑是在 `setup()` 阶段调用：

```text
yield from simulate_data_download(env, replica)
```

从而根据数据路径和 StorageIndex 触发数据下载。

### `analysis.py`

指标导出与分析文件。

该文件负责导出每个场景的调度、下载、网络流、部署和调用指标，并生成：
- `data_locality_summary.csv`：单场景摘要
- `candidate_vs_actual_join.csv`：candidate 估算 vs download 实际 join
- `data_locality_comparison.csv`：两场景 side-by-side
- `data_locality_paper_highlight.csv`：论文 demo 关键摘要（含 speedup_ratio 和 theoretical 反算）

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。