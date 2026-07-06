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
skippy_scheduler_result.csv
skippy_scheduler_candidate.csv
schedule.csv
allocation.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv
flow.csv
skippy_scheduler_summary.csv
skippy_selected_node_distribution.csv
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
