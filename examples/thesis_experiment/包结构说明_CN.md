# thesis_experiment 包结构说明

`thesis_experiment` 是论文实验组织样例包，用于把函数画像、节点状态、请求 trace、策略 case、控制决策和结果分析组织成一个可运行闭环。

## 目录结构

```text
thesis_experiment/
├── inputs/
│   ├── experiment_cases.csv
│   ├── function_profile.csv
│   ├── node_state.csv
│   └── workload_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── loader.py
├── main.py
├── models.py
├── progress.py
├── README_CN.md
├── runner.py
└── simulator.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取实验输入；
2. 创建实验运行器；
3. 执行全部实验 case；
4. 导出 CSV 结果和 Markdown 报告；
5. 在控制台打印策略摘要。

### `inputs/function_profile.csv`

函数画像输入文件。

用于定义冷启动代价、warm 执行时间、镜像拉取代价、数据拉取代价、资源需求和偏好区域。

### `inputs/node_state.csv`

节点状态输入文件。

用于定义边缘节点资源余量、负载、网络延迟、区域和加速能力。

### `inputs/workload_trace.csv`

请求 trace 输入文件。

用于描述请求到达时间、目标函数、来源区域和负载阶段。

### `inputs/experiment_cases.csv`

实验 case 配置文件。

用于定义不同策略是否启用 `R_cache`、`R_load` 和缓存感知调度。

### `models.py`

数据结构定义文件。

该文件定义：

```text
FunctionProfile
NodeState
WorkloadEvent
ExperimentCase
WarmEntry
RequestResult
ControlDecision
CandidateScore
EvictionEvent
```

### `loader.py`

输入读取文件。

负责读取所有 CSV 输入。

### `simulator.py`

trace-driven 实验模拟器。

负责执行单个实验 case，并记录请求结果、控制决策、候选节点评分和驱逐事件。

### `runner.py`

多 case 运行器。

负责依次运行所有实验 case，并合并结果。

### `progress.py`

进度条兼容封装。

优先使用 `tqdm`，缺失时自动回退。

### `analysis.py`

结果导出与报告生成文件。

负责生成：

```text
thesis_request_result.csv
thesis_control_decision.csv
thesis_candidate_score.csv
thesis_eviction_event.csv
thesis_policy_summary.csv
thesis_function_summary.csv
thesis_phase_summary.csv
thesis_control_summary.csv
thesis_baseline_comparison.csv
thesis_experiment_report.md
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果和 Markdown 报告。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/thesis_experiment/main.py
```

## 样例定位

该样例属于论文实验组织入口。它承接前面 `cache_policy`、`cache_decision`、`cache_aware_autoscaling`、`edge_cache_scheduler` 等样例，把策略、控制、调度和指标导出整合到一个面向论文结果分析的闭环中。
