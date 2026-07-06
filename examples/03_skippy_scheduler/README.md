# 03_skippy_scheduler：faas-sim 原生 Skippy 默认调度机制样例

本样例用于演示 faas-sim 中默认 Skippy 调度机制，重点展示资源过滤、节点可行性判断、节点选择和 `SchedulingResult` 的含义。

## 运行方式

将 `skippy_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/03_skippy_scheduler/main.py
```

## 样例目标

该样例主要回答以下问题：

1. Skippy 默认调度器如何参与 faas-sim 函数副本部署；
2. 资源过滤如何影响候选节点数量；
3. `SchedulingResult.suggested_host` 表示什么；
4. `SchedulingResult.feasible_nodes` 表示什么；
5. `SchedulingResult.needed_images` 表示什么；
6. 如何导出调度过程指标。

## 输出文件

运行结束后，结果会保存到：

```text
examples/03_skippy_scheduler/outputs/
```

主要包括：

```text
skippy_scheduler_result.csv             # 每次调度的 SchedulingResult（论文关键源数据）
skippy_scheduler_candidate.csv          # 每个 pod 的候选节点快照（前 30 个）
skippy_feasible_nodes_per_pod.csv       # 每个 pod 的可行节点数（论文 demo 关键图）
skippy_node_scheduling_stats.csv        # 按 node 详细分组的调度统计（论文关键图）
skippy_scheduler_summary.csv            # 增强版摘要（含 max/min feasible_nodes / 首调 vs 复用）
skippy_selected_node_distribution.csv   # selected_node × needed_images 分组
schedule.csv
allocation.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv
flow.csv
```

### 论文 demo 关键图说明

**1. `skippy_feasible_nodes_per_pod.csv`** —— 每个 pod 的可行节点数

列：pod_name / all_nodes / feasible_nodes_full / returned_feasible_nodes / needed_images_count / selected_node

画图：
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("outputs/skippy_feasible_nodes_per_pod.csv")
fig, ax = plt.subplots(figsize=(8, 4))
x = range(len(df))
ax.bar(x, df.all_nodes, color="lightgray", label="all_nodes")
ax.bar(x, df.feasible_nodes_full, color="steelblue", label="feasible_nodes_full")
ax.set_xticks(list(x))
ax.set_xticklabels(df.pod_name, rotation=20, ha="right")
ax.set_ylabel("Node count")
ax.set_title("Skippy resource filtering: candidates vs feasible nodes")
ax.legend()
plt.tight_layout()
plt.show()
```

**2. `skippy_node_scheduling_stats.csv`** —— 按 node 详细分组

列：node_name / arch / node_type / scheduled_pod_count

画图：
```python
df = pd.read_csv("outputs/skippy_node_scheduling_stats.csv")
# 按 arch 分组看调度分布
print(df.groupby("arch")["scheduled_pod_count"].sum())
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 注册函数镜像；
3. 构造不同资源请求的函数部署；
4. 创建 `Simulation`；
5. 替换为可观测 Skippy 调度器；
6. 运行请求负载；
7. 导出调度结果指标。

### `scheduler.py`

可观测 Skippy 调度器文件。

该文件提供：

```text
InstrumentedSkippyScheduler
```

它继承 Skippy 原生 `Scheduler`，保留默认调度语义，只额外记录候选节点、可行节点和调度结果。

### `simulator.py`

函数执行模拟器文件。

该文件提供稳定函数执行时间，保证样例重点集中在调度结果，而不是执行模型差异。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `skippy_scheduler_result`、`skippy_scheduler_candidate`、`schedule` 等 DataFrame，并生成调度摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
