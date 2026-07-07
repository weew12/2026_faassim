# 23_thesis_experiment：论文实验组织样例

本样例用于组织一个最小但完整的论文实验闭环。它不直接依赖 faas-sim 核心接口，而是采用 trace-driven 方式模拟函数画像、节点状态、缓存状态、扩缩容决策和调度选择，便于稳定生成论文实验所需的 CSV 指标和 Markdown 报告。

**本样例是论文级整合 demo**：整合 17/18/19/20/22 的核心机制（policy 评分 + R_cache/R_load + 节点选择 + 扩缩容决策）到一个 trace-driven 框架。

## 运行方式

将 `23_thesis_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/23_thesis_experiment/main.py
```

## 实验目标

该样例主要回答以下问题：

1. 如何把函数画像、节点状态、请求 trace 和实验 case 组织成论文实验输入；
2. 如何同时输出请求级、函数级、阶段级和策略级指标；
3. 如何对比 `LoadOnly`、`FaasCache` 和 `CacheAwareJoint` 三类策略；
4. 如何记录 `R_cache`、`R_load` 和 `R_desired` 的控制决策；
5. 如何生成候选节点评分、缓存命中率、冷启动惩罚和 Markdown 实验报告；
6. **如何做 result×candidate 关联验证**：CacheAwareJoint 的 selected_node 必须是 max-score，且 cache_hit 一致；
7. **如何做 request×decision 关联验证**：result 跟 decision 的 R_cache / R_load / R_desired 完全一致；
8. **如何做数据自洽段**（18 个不变量）。

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

默认输入：3 个 case / 5 个函数 / 6 个节点（4 edge + 2 cloud）/ 35 个 request / 105 个 result（35 × 3 case）。

## 输出文件

运行结束后，结果会保存到：

```text
examples/23_thesis_experiment/outputs/
```

主要文件：

```text
thesis_request_result.csv              # 请求级结果（105 行 = 3 case × 35 request）
thesis_control_decision.csv            # 每 request 的 R_cache/R_load/R_desired 控制决策
thesis_candidate_score.csv             # 每个 (case, request) 的所有候选节点评分
thesis_eviction_event.csv              # 驱逐事件
thesis_policy_summary.csv              # per-(case, policy) 摘要
thesis_function_summary.csv            # per-(case, policy, function) 摘要
thesis_phase_summary.csv               # per-(case, policy, phase) 摘要
thesis_control_summary.csv             # per-(case, policy, action, reason) 摘要
thesis_baseline_comparison.csv         # 以 LoadOnly 为 baseline 的相对改进
thesis_result_candidate_join.csv       # result × candidate 关联（论文 demo 关键证据）
thesis_request_decision_join.csv       # request × decision 关联（论文 demo 关键证据）
thesis_paper_highlight.csv             # 论文 demo 关键摘要
thesis_experiment_report.md            # Markdown 实验报告
```

## 关键导出

### 1. `thesis_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                            value
warm_hit_rate__cache_aware_joint                                0.5714
warm_hit_rate__faascache                                         0.5429
warm_hit_rate__load_only                                         0.2000
image_cache_hit_rate__cache_aware_joint                          0.8571
image_cache_hit_rate__faascache                                  0.3714
image_cache_hit_rate__load_only                                  0.3714
data_cache_hit_rate__cache_aware_joint                            0.8571
data_cache_hit_rate__faascache                                   0.3714
data_cache_hit_rate__load_only                                   0.3714
avg_latency__cache_aware_joint                                   0.8547
avg_latency__faascache                                           1.4410
avg_latency__load_only                                           1.9095
avg_latency_reduction__cache_aware_joint_vs_load_only            0.5524
cold_start_penalty_reduction__cache_aware_joint_vs_load_only      0.5105
image_cache_hit_rate_improvement__cache_aware_joint_vs_load_only 0.4857
data_cache_hit_rate_improvement__cache_aware_joint_vs_load_only  0.4857
avg_latency_reduction__cache_aware_joint_vs_faascache             0.4068
image_cache_hit_rate_improvement__cache_aware_joint_vs_faascache  0.4857
data_cache_hit_rate_improvement__cache_aware_joint_vs_faascache   0.4857
r_dominant_summary__cache_aware_joint                            r_cache=0.971, r_load=1.000, r_desired=1.000; max=1.000
r_dominant_summary__faascache                                    r_cache=0.971, r_load=0.000, r_desired=0.971; max=0.971
r_dominant_summary__load_only                                    r_cache=0.000, r_load=1.000, r_desired=1.000; max=1.000
result_candidate_consistency                                     1.0000
result_candidate_matched                                         105
result_candidate_total                                           105
request_decision_consistency                                     1.0000
request_decision_matched                                         105
request_decision_total                                           105
```

**关键发现**（论文 demo 一句话核心）：

**`CacheAwareJoint` 相比 `LoadOnly` 基线**：
- **avg_latency 降 55.24%**（1.91s → 0.85s）
- **cold_start_penalty 降 51.05%**（35.85s → 17.55s）
- **warm_hit_rate 提升 37.1 pp**（20% → 57.1%）
- **image_cache_hit_rate 提升 48.6 pp**（37.1% → 85.7%）
- **data_cache_hit_rate 提升 48.6 pp**（37.1% → 85.7%）

**`CacheAwareJoint` 相比 `FaasCache`**：
- **avg_latency 降 40.68%**（1.44s → 0.85s）
- **image/data_cache_hit_rate 提升 48.6 pp**（37.1% → 85.7%）—— 关键论文 demo：**CacheAwareJoint 真的把"调度感知"加上之后，image/data cache hit 翻倍**

**R_cache vs R_load 主导分析**（论文核心结论）：

| case | R_cache | R_load | R_desired | 主导 |
|---|---|---|---|---|
| LoadOnly | 0.000 | 1.000 | 1.000 | R_load 单独 |
| FaasCache | 0.971 | 0.000 | 0.971 | R_cache 单独 |
| **CacheAwareJoint** | **0.971** | **1.000** | **1.000** | **R_load 主导（R_cache 也起作用）** |

**关键发现**：CacheAwareJoint 是**唯一同时 R_cache>0 且 R_load>0** 的策略，验证 `R_desired = max(R_cache, R_load)` 公式在论文中真正生效。

**result×candidate 关联 100% 一致**（105/105）：选中的节点都在 candidate 评分里、cache_hit 一致、latency 一致。

**request×decision 关联 100% 一致**（105/105）：result 跟 decision 的 R_cache / R_load / R_desired 完全一致。

### 2. `thesis_result_candidate_join.csv` —— result × candidate 关联（论文 demo 关键证据）

按 (case_id, policy_name, request_id) 关联 result 和 candidate：

| case | policy | selected_node | selected_total_score | max_total_score | result_warm_hit | result_latency | match |
|---|---|---|---|---|---|---|---|
| cache_aware_joint | CacheAwareJoint | edge-a-1 | 1.0 | 1.0 | True | 0.42 | True |
| cache_aware_joint | CacheAwareJoint | edge-a-1 | 1.0 | 1.0 | True | 0.30 | True |
| ... | ... | ... | ... | ... | ... | ... | ... |

预期 105 行，**`match` 全部 True**。

**验证规则**：
- `cache_aware_joint` 严格要求 `selected_node` 是 max-score 节点；
- `faascache` / `load_only` 不要求 max-score（它们的调度逻辑不基于 candidate 评分）；
- 三个 case 都要求 `result.warm_hit == candidate.warm_hit`、`result.image_cache_hit == candidate.image_cache_hit`、`result.data_cache_hit == candidate.data_cache_hit`；
- 三个 case 都要求 `result.latency` 跟 `candidate.estimated_latency` 接近（误差 < 0.01s）。

### 3. `thesis_request_decision_join.csv` —— request × decision 关联（论文 demo 关键证据）

按 (case_id, policy_name, request_id) 关联 result 和 control_decision：

| case | policy | result_r_cache | decision_r_cache | result_r_load | decision_r_load | match |
|---|---|---|---|---|---|---|
| cache_aware_joint | CacheAwareJoint | 1 | 1 | 1 | 1 | True |
| faascache | FaasCache | 1 | 1 | 0 | 0 | True |
| ... | ... | ... | ... | ... | ... | ... |

预期 105 行，**`match` 全部 True**。

**验证规则**：
- `result.r_cache == decision.r_cache`
- `result.r_load == decision.r_load`
- `result.r_desired == decision.r_desired`

### 4. 论文 demo 关键图 —— 三策略命中率对比

```python
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv("examples/23_thesis_experiment/outputs/thesis_policy_summary.csv")
metrics = ["warm_hit_rate", "image_cache_hit_rate", "data_cache_hit_rate"]
x = np.arange(len(metrics))
width = 0.25

fig, ax = plt.subplots(figsize=(8, 4))
for i, case in enumerate(df["case_id"]):
    values = [df.loc[df["case_id"] == case, m].iloc[0] for m in metrics]
    ax.bar(x + (i - 1) * width, values, width, label=case)

ax.set_xticks(x)
ax.set_xticklabels(["warm", "image", "data"])
ax.set_ylabel("hit_rate")
ax.set_ylim(0, 1.1)
ax.set_title("Thesis: three cache dimension hit rates by case")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**18 个核心不变量**应同时满足（18/18 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `request_result` 行数 = 105（3 case × 35 request） | self-check |
| 2 | `candidate_score` 行数 > request 行数（630 > 105） | self-check |
| 3 | `policy_summary` 行数 = 3 | self-check |
| 4-6 | per-case `request_count` = 35 | self-check |
| 7 | `baseline_comparison` 行数 = 3 | self-check |
| 8 | `baseline_comparison` 包含 `load_only` | self-check |
| 9 | result×candidate join 100% match | self-check（105/105） |
| 10 | cache_aware_joint 100% max-score | self-check（35/35） |
| 11 | request×decision join 100% match | self-check（105/105） |
| 12-14 | paper highlight 3 个 warm_hit_rate 跟 policy_summary 一致 | self-check |
| 15 | paper highlight 改善值跟 summary 一致 | self-check |
| 16 | cache_aware_joint ≥ faascache ≥ load_only 顺序 | self-check（ca=0.5714, fc=0.5429, lo=0.2000） |
| 17 | paper highlight `result_candidate_consistency` = 1.0 | self-check |
| 18 | paper highlight `request_decision_consistency` = 1.0 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== thesis_experiment self-check ===
INFO:analysis:  [PASS] request_result_row_count : requests=105, expected=105
INFO:analysis:  [PASS] candidate_score_count : candidates=630, requests=105
INFO:analysis:  [PASS] policy_summary_row_count : summary rows=3, expected=3
INFO:analysis:  [PASS] case_request_count__cache_aware_joint : request_count=35
INFO:analysis:  [PASS] case_request_count__faascache : request_count=35
INFO:analysis:  [PASS] case_request_count__load_only : request_count=35
INFO:analysis:  [PASS] baseline_comparison_row_count : 3
INFO:analysis:  [PASS] baseline_comparison_has_load_only
INFO:analysis:  [PASS] result_candidate_join_match : 105/105
INFO:analysis:  [PASS] cache_aware_joint_candidate_max_score : 35/35
INFO:analysis:  [PASS] request_decision_join_match : 105/105
INFO:analysis:  [PASS] paper_highlight_warm_hit_rate__cache_aware_joint : 0.571429
INFO:analysis:  [PASS] paper_highlight_warm_hit_rate__faascache : 0.542857
INFO:analysis:  [PASS] paper_highlight_warm_hit_rate__load_only : 0.200000
INFO:analysis:  [PASS] paper_highlight_image_cache_improvement : 0.485714
INFO:analysis:  [PASS] cache_aware_joint_ge_faascache_ge_load_only : ca=0.5714, fc=0.5429, lo=0.2000
INFO:analysis:  [PASS] paper_highlight_result_candidate_consistency : 1.0000
INFO:analysis:  [PASS] paper_highlight_request_decision_consistency : 1.0000
INFO:analysis:=== 18 passed, 0 failed ===
```

## 目录结构

```text
23_thesis_experiment/
├── inputs/                              # 4 个输入 csv
│   ├── function_profile.csv
│   ├── node_state.csv
│   ├── workload_trace.csv
│   └── experiment_cases.csv
├── outputs/                             # 运行输出
├── __init__.py
├── analysis.py                          # 摘要 + 2 个 join + paper highlight + self-check
├── loader.py                            # 4 个 csv 读取
├── main.py                              # 入口
├── models.py                            # 数据结构
├── progress.py                          # tqdm 兼容
├── runner.py                            # ThesisExperimentRunner（多 case）
└── simulator.py                         # trace-driven 模拟器
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数画像 / 节点状态 / 请求 trace / 实验 case；
2. 创建 ThesisExperimentRunner；
3. 执行全部实验 case；
4. 导出 CSV 结果 + Markdown 报告 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/`

4 个输入 csv 文件。

### `models.py`

数据结构定义文件。

定义 `FunctionProfile` / `NodeState` / `WorkloadEvent` / `ExperimentCase` / `WarmEntry` / `RequestResult` / `ControlDecision` / `CandidateScore` / `EvictionEvent`。

### `loader.py`

输入读取文件。

读取 4 个 csv 输入。

### `simulator.py`

trace-driven 实验模拟器。

执行单个实验 case，记录请求结果、控制决策、候选节点评分、驱逐事件。

### `runner.py`

多 case 运行器。

依次运行所有实验 case，合并结果。

### `progress.py`

进度条兼容封装。

优先使用 `tqdm`，缺失时回退。

### `analysis.py`

结果导出 + 2 个 join + 论文 demo 关键摘要 + 数据自洽段文件。

- 4 个原始 summary（policy / function / phase / control）；
- `build_baseline_comparison`：以 LoadOnly 为 baseline 的相对改进；
- `build_result_candidate_join`：result × candidate 关联（论文 demo 关键证据）；
- `build_request_decision_join`：request × decision 关联（论文 demo 关键证据）；
- `build_paper_highlight`：3 维度 hit_rate + 改善值 + R_cache vs R_load 主导 + consistency；
- 数据自洽段：18 个不变量。

### `outputs/`

运行结果输出目录。

包含 12 个文件（4 原始 + 4 summary + 1 baseline + 2 join + 1 paper highlight + 1 md report）。
