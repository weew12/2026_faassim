# 22_edge_cache_scheduler：边缘缓存感知调度样例

本样例用于演示边缘缓存感知调度。与只考虑资源或轮转的调度方式不同，边缘缓存感知调度同时考虑函数 warm 实例缓存、镜像缓存、数据缓存、边缘区域亲和性和节点负载。

**本样例不跑 faas-sim Simulation，是 in-memory 调度算法实验**（跟 19 同类，但更复杂：3 个缓存维度 + 资源 + 区域 + 负载）。

## 运行方式

将 `22_edge_cache_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/22_edge_cache_scheduler/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何把边缘节点状态、函数画像、缓存状态和请求 trace 组织为调度输入；
2. 如何区分函数 warm 实例缓存、镜像缓存和数据缓存；
3. 如何在候选节点上计算缓存命中、区域亲和性、资源余量和负载惩罚；
4. 如何对比缓存无感知调度和边缘缓存感知调度；
5. 如何导出候选节点评分和请求级调度结果；
6. **如何做 result×candidate 关联验证**：每个 request 选中的节点确实是 max-score，且 cache_hit / estimated_latency 跟 candidate 评分一致（论文 demo 关键证据）；
7. **如何做数据自洽段**（21 个不变量）。

## 调度策略

样例包含两个策略：

```text
edge_round_robin     缓存无感知基线，按可行节点轮转
edge_cache_aware     边缘缓存感知调度，综合缓存、资源、区域和负载评分
```

## 调度评分

`edge_cache_aware` 使用最小综合评分：

```text
total_score = cache_score + resource_score + locality_score - load_penalty - latency_penalty
```

其中：

```text
cache_score       函数 warm 缓存、镜像缓存和数据缓存得分
resource_score    CPU 与内存空闲资源得分
locality_score    请求来源区域与函数偏好区域匹配得分
load_penalty      当前节点负载惩罚
latency_penalty   网络延迟惩罚
```

该公式用于演示机制，后续可以替换为论文第四章中的缓存状态与容量画像协同调度评分。

## 输入文件

节点状态、函数画像、缓存快照、请求 trace 分别位于：

```text
inputs/node_state_snapshot.csv
inputs/function_profile.csv
inputs/cache_state_snapshot.csv
inputs/request_trace.csv
```

默认输入：6 个节点（4 edge + 2 cloud） / 5 个函数 / 15 个 cache 缓存项 / 15 个 request。

## 输出文件

运行结束后，结果会保存到：

```text
examples/22_edge_cache_scheduler/outputs/
```

主要文件：

```text
edge_cache_scheduling_result.csv            # 请求级调度结果（30 行 = 2 policy × 15 request）
edge_cache_candidate_score.csv             # 每个 (policy, request) 的所有候选节点评分
edge_cache_result_candidate_join.csv       # result × candidate 关联（论文 demo 关键证据）
edge_cache_policy_summary.csv              # per-policy 摘要
edge_cache_node_summary.csv                # per-(policy, selected_node) 摘要
edge_cache_function_summary.csv            # per-(policy, function) 摘要
edge_cache_policy_paper_highlight.csv      # 论文 demo 关键摘要
```

## 关键导出

### 1. `edge_cache_policy_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                            value
function_cache_hit_rate__edge_cache_aware                        0.9333
function_cache_hit_rate__edge_round_robin                        0.2000
image_cache_hit_rate__edge_cache_aware                           1.0000
image_cache_hit_rate__edge_round_robin                           0.2667
data_cache_hit_rate__edge_cache_aware                            0.9333
data_cache_hit_rate__edge_round_robin                            0.2667
avg_estimated_latency__edge_cache_aware                          0.3629
avg_estimated_latency__edge_round_robin                          2.0212
total_cold_start_penalty__edge_cache_aware                       2.400
total_cold_start_penalty__edge_round_robin                       15.900
function_cache_hit_rate_improvement__edge_cache_aware_over_edge_round_robin   0.7333
image_cache_hit_rate_improvement__edge_cache_aware_over_edge_round_robin      0.7333
data_cache_hit_rate_improvement__edge_cache_aware_over_edge_round_robin       0.6667
avg_estimated_latency_reduction__edge_cache_aware_over_edge_round_robin      0.8204
cold_start_penalty_reduction__edge_cache_aware_over_edge_round_robin         0.8491
result_candidate_consistency                                    1.0000
result_candidate_matched                                        30
result_candidate_total                                          30
```

**关键发现**：
- **3 个缓存维度命中率大幅提升**：function +73.3pp（20% → 93.3%）、image +73.3pp（27% → 100%）、data +66.7pp（27% → 93.3%）。
- **avg_estimated_latency 降低 82%**（2.02s → 0.36s）。
- **cold_start_penalty 降低 85%**（15.9s → 2.4s）。
- **result_candidate_consistency = 1.0**（30/30）：选中的节点确实是 max-score，且 cache_hit / estimated_latency 跟 candidate 评分一致。

### 2. `edge_cache_result_candidate_join.csv` —— result × candidate 关联（论文 demo 关键证据）

按 (policy_name, request_id) 关联 result 和 candidate：

| policy | request_id | function | selected_node | selected_total_score | max_total_score | cache_hit | match |
|---|---|---|---|---|---|---|---|
| edge_cache_aware | 1 | img-resize | edge-a-1 | 13.44 | 13.44 | True | True |
| edge_cache_aware | 2 | fft | edge-a-1 | 13.44 | 13.44 | True | True |
| ... | ... | ... | ... | ... | ... | ... | ... |

预期 30 行，**`match` 全部 True**。

**验证规则**：
- `selected_node.total_score == max(candidate_score.total_score)`（选中的就是 max-score）
- `result.function_cache_hit == candidate.function_cache_hit`（cache_hit 一致）
- `result.estimated_latency == candidate.estimated_latency`（latency 一致）

### 3. per-function 摘要（论文 demo 关键）

| function | edge_round_robin function_cache_hit | edge_cache_aware function_cache_hit |
|---|---|---|
| img-resize | 25% | **100%** |
| fft | 0% | **100%** |
| json-parse | 33% | **100%** |
| ml-infer | 33% | **100%** |
| video-analytics | 0% | **50%** |

**关键发现**：
- `edge_cache_aware` 把所有 4 个高频函数（img-resize / fft / json-parse / ml-infer）的命中率从 0-33% 提升到 100%。
- `video-analytics` 是低频函数（2 个 request），50% 命中率合理（1 个 cache miss，因为 cache 节点容量限制）。

### 4. 论文 demo 关键图 —— 三个缓存维度命中率对比

```python
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

df = pd.read_csv("examples/22_edge_cache_scheduler/outputs/edge_cache_policy_summary.csv")
metrics = ["function_cache_hit_rate", "image_cache_hit_rate", "data_cache_hit_rate"]
x = np.arange(len(metrics))
width = 0.35

fig, ax = plt.subplots(figsize=(8, 4))
for i, policy in enumerate(df["policy_name"]):
    values = [df.loc[df["policy_name"] == policy, m].iloc[0] for m in metrics]
    ax.bar(x + (i - 0.5) * width, values, width, label=policy)

ax.set_xticks(x)
ax.set_xticklabels(["function", "image", "data"])
ax.set_ylabel("hit_rate")
ax.set_ylim(0, 1.1)
ax.set_title("Edge cache scheduler: three cache dimension hit rates")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**21 个核心不变量**应同时满足（21/21 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `scheduling_result` 行数 = 30（2 policy × 15 request） | self-check |
| 2 | `candidate_score` 行数 > result 行数（每 request 多个 candidate） | self-check |
| 3 | `policy_summary` 行数 = 2 | self-check |
| 4-5 | per-policy `request_count` = 15 | self-check |
| 6-11 | 6 个 hit_rate 都在 [0, 1] 范围内 | self-check |
| 12 | result×candidate join 100% match | self-check（30/30） |
| 13-18 | paper highlight 6 个 hit_rate 跟 policy_summary 一致 | self-check |
| 19 | paper highlight 改善值跟 summary 一致 | self-check |
| 20 | edge_cache_aware 命中率 >= edge_round_robin | self-check |
| 21 | paper highlight `result_candidate_consistency` = 1.0 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== edge_cache_scheduler self-check ===
INFO:analysis:  [PASS] scheduling_result_row_count : results=30, expected=30
INFO:analysis:  [PASS] candidate_score_count : candidates=180, results=30
INFO:analysis:  [PASS] policy_summary_row_count : summary rows=2, expected=2
INFO:analysis:  [PASS] policy_request_count__edge_cache_aware : request_count=15, expected=15
INFO:analysis:  [PASS] policy_request_count__edge_round_robin : request_count=15, expected=15
INFO:analysis:  [PASS] function_cache_hit_rate_in_range__edge_cache_aware : function_cache_hit_rate=0.9333
INFO:analysis:  [PASS] image_cache_hit_rate_in_range__edge_cache_aware : image_cache_hit_rate=1.0000
INFO:analysis:  [PASS] data_cache_hit_rate_in_range__edge_cache_aware : data_cache_hit_rate=0.9333
INFO:analysis:  [PASS] function_cache_hit_rate_in_range__edge_round_robin : function_cache_hit_rate=0.2000
INFO:analysis:  [PASS] image_cache_hit_rate_in_range__edge_round_robin : image_cache_hit_rate=0.2667
INFO:analysis:  [PASS] data_cache_hit_rate_in_range__edge_round_robin : data_cache_hit_rate=0.2667
INFO:analysis:  [PASS] result_candidate_join_match : matched=30/30
INFO:analysis:  [PASS] paper_highlight_function_cache_hit_rate__edge_cache_aware : 0.933333
INFO:analysis:  [PASS] paper_highlight_image_cache_hit_rate__edge_cache_aware : 1.000000
INFO:analysis:  [PASS] paper_highlight_data_cache_hit_rate__edge_cache_aware : 0.933333
INFO:analysis:  [PASS] paper_highlight_function_cache_hit_rate__edge_round_robin : 0.200000
INFO:analysis:  [PASS] paper_highlight_image_cache_hit_rate__edge_round_robin : 0.266667
INFO:analysis:  [PASS] paper_highlight_data_cache_hit_rate__edge_round_robin : 0.266667
INFO:analysis:  [PASS] paper_highlight_function_cache_hit_rate_improvement : 0.733333
INFO:analysis:  [PASS] edge_cache_aware_beats_edge_round_robin : 0.9333 >= 0.2000
INFO:analysis:  [PASS] paper_highlight_result_candidate_consistency : 1.0000
INFO:analysis:=== 21 passed, 0 failed ===
```

## 目录结构

```text
22_edge_cache_scheduler/
├── inputs/                              # 4 个输入 csv
│   ├── node_state_snapshot.csv
│   ├── function_profile.csv
│   ├── cache_state_snapshot.csv
│   └── request_trace.csv
├── outputs/                             # 运行输出
├── __init__.py
├── analysis.py                          # 摘要 + result×candidate join + paper + self-check
├── cache_index.py                       # CacheIndex（function / image / data 三种缓存查询）
├── loader.py                            # 4 个 csv 读取
├── main.py                              # 入口
├── models.py                            # 数据结构
├── runner.py                            # EdgeCacheSchedulerRunner
└── scheduler.py                         # EdgeRoundRobinScheduler + EdgeCacheAwareScheduler
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取节点状态 / 函数画像 / 缓存快照 / 请求 trace；
2. 运行两个调度策略；
3. 导出对比结果 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/node_state_snapshot.csv`

节点状态输入文件。

默认 6 个节点（4 edge + 2 cloud）。

### `inputs/function_profile.csv`

函数画像输入文件。

默认 5 个函数（img-resize / json-parse / fft / video-analytics / ml-infer）。

### `inputs/cache_state_snapshot.csv`

缓存状态输入文件。

默认 15 个 (function, image, data) × node 缓存项。

### `inputs/request_trace.csv`

请求 trace 输入文件。

默认 15 个 request（time 从 0.0 到 7.0）。

### `models.py`

数据结构定义文件。

定义 `NodeState` / `FunctionProfile` / `CacheEntry` / `RequestEvent` / `CandidateScore` / `SchedulingResult`。

### `cache_index.py`

缓存索引文件。

用于查询 function cache / image cache / data cache 是否命中。

### `scheduler.py`

调度器文件。

- `EdgeRoundRobinScheduler`：轮转选择 server 节点；
- `EdgeCacheAwareScheduler`：综合 cache + resource + locality + load + latency 评分选 max-score 节点。

### `runner.py`

实验执行器文件。

将请求 trace 喂给两个策略，收集 request_results / candidate_scores。

### `analysis.py`

结果导出 + result×candidate 关联 + 论文 demo 关键摘要 + 数据自洽段文件。

- 3 个原始 summary（policy / node / function）；
- `build_result_candidate_join`：验证 selected_node 是 max-score；
- `build_paper_highlight`：3 维度 hit_rate + 改善值 + consistency；
- 数据自洽段：21 个不变量。

### `outputs/`

运行结果输出目录。

包含 7 个 CSV（2 原始 + 3 summary + 1 join + 1 paper highlight）。
