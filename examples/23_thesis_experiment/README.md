# thesis_experiment：论文实验组织样例

本样例用于组织一个最小但完整的论文实验闭环。它不直接依赖 faas-sim 核心接口，而是采用 trace-driven 方式模拟函数画像、节点状态、缓存状态、扩缩容决策和调度选择，便于稳定生成论文实验所需的 CSV 指标和 Markdown 报告。

## 运行方式

将 `thesis_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/23_thesis_experiment/main.py
```

## 实验目标

该样例主要回答以下问题：

1. 如何把函数画像、节点状态、请求 trace 和实验 case 组织成论文实验输入；
2. 如何同时输出请求级、函数级、阶段级和策略级指标；
3. 如何对比 `LoadOnly`、`FaasCache` 和 `CacheAwareJoint` 三类策略；
4. 如何记录 `R_cache`、`R_load` 和 `R_desired` 的控制决策；
5. 如何生成候选节点评分、缓存命中率、冷启动惩罚和 Markdown 实验报告。

## 实验策略

默认包含三个实验 case：

```text
LoadOnly          仅根据 R_load 保留运行副本，作为负载扩缩容基线
FaasCache         根据冷启动收益进行函数实例缓存，调度不感知缓存位置
CacheAwareJoint   组合 R_cache 与 R_load，并在节点选择中利用缓存状态
```

其中 `CacheAwareJoint` 使用：

```text
R_desired = max(R_cache, R_load)
```

并在节点选择时综合函数 warm 缓存、镜像缓存、数据缓存、边缘区域、节点负载和网络延迟。

## 输入文件

函数画像：

```text
inputs/function_profile.csv
```

节点状态：

```text
inputs/node_state.csv
```

请求 trace：

```text
inputs/workload_trace.csv
```

实验 case：

```text
inputs/experiment_cases.csv
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/23_thesis_experiment/outputs/
```

主要包括：

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

## 结果解读

重点查看：

```text
thesis_policy_summary.csv
```

其中包含：

```text
warm_hit_rate
image_cache_hit_rate
data_cache_hit_rate
avg_latency
p95_latency
total_cold_start_penalty
avg_r_cache
avg_r_load
avg_r_desired
```

再查看：

```text
thesis_baseline_comparison.csv
```

可以看到各策略相对于 `LoadOnly` 的平均延迟变化、冷启动惩罚降低比例和 warm hit rate 提升。

## 设计边界

本样例是论文实验组织模板，不直接调用 faas-sim 的核心调度器或 FaaSSystem 接口。这样做的目的是避免不同源码版本之间的接口差异影响实验组织样例运行。后续若需要真实 faas-sim 联动，可把本样例中的策略、评分和指标字段迁移到具体 simulator / scheduler / autoscaler 中。

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
