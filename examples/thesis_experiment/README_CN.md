# thesis_experiment：论文实验组织样例

本样例用于组织一个最小但完整的论文实验闭环。它不直接依赖 faas-sim 核心接口，而是采用 trace-driven 方式模拟函数画像、节点状态、缓存状态、扩缩容决策和调度选择，便于稳定生成论文实验所需的 CSV 指标和 Markdown 报告。

## 运行方式

将 `thesis_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/thesis_experiment/main.py
```

## 文件结构

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
examples/thesis_experiment/outputs/
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

## 后续扩展

该样例可以继续扩展为正式论文实验入口：

1. 接入真实 faas-sim 事件输出；
2. 增加多随机种子、多 workload、多容量预算批量实验；
3. 加入 FaasCache、S-Cache、OnCoLa 等更完整 baseline；
4. 增加消融实验，如去掉 `R_cache`、去掉 `R_load`、去掉缓存感知调度；
5. 自动生成论文图表数据和章节实验分析草稿。
