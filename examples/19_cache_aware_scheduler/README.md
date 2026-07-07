# 19_cache_aware_scheduler：缓存状态感知调度样例

本样例用于演示缓存状态感知调度的最小实验闭环。调度器读取节点级函数 warm 实例缓存状态，在候选节点中优先选择已有目标函数缓存的节点，从而降低冷启动惩罚。

**跟 13 一样有 ether.scenarios.urbansensing 状态污染坑**：用 ether.core 直接构造 4-server 最小拓扑。

## 运行方式

将 `19_cache_aware_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/19_cache_aware_scheduler/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何读取节点级函数 warm 实例缓存快照；
2. 如何在调度阶段识别目标函数是否已有缓存节点；
3. 如何对候选节点计算 cache-aware score；
4. 如何与缓存无感知调度进行对比；
5. 如何导出候选节点评分、最终调度结果和请求级缓存命中情况；
6. **如何做 probe×invocation join 验证**：simulator 派发的 final_duration == faas-sim 记录的 t_exec；
7. **如何做数据自洽段**（15 个不变量）。

## 输入文件

缓存快照位于：

```text
inputs/cache_state_snapshot.csv
```

字段包括：

```text
function_name
node_name
warm_replicas
cached
last_access_age
avg_cold_start
memory_units
```

请求负载位于：

```text
inputs/workload.csv
```

字段包括：

```text
request_id
function_name
arrival_time
```

默认输入：
- 4 个函数：img-resize / fft / json-parse / ml-infer
- 4 个 cache 节点：img-resize→server_0, fft→server_1, json-parse→server_0, ml-infer→server_2
- 10 个 request

## 拓扑构造

```text
DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0
                                       |
                                       -- link_server_1 -- server_1
                                       |
                                       -- link_server_2 -- server_2
                                       |
                                       -- link_server_3 -- server_3
```

**为什么不复用 UrbanSensingScenario**：
ether.scenarios.urbansensing 在连续构造时会返回不同的节点集（server_0..9 / server_10..19 / ... / server_70..79），导致 cache_blind 和 cache_aware 两个 scenario 各自跑在不同 topology，cache snapshot 完全失效（server_0/1/2 对不上 server_10..19）。

这里用 ether.core 直接构造 4 个 server 节点：
- server_0：img-resize + json-parse 缓存
- server_1：fft 缓存
- server_2：ml-infer 缓存
- server_3：无缓存（cache_blind 轮转会选它，cache_aware 会避开它）

通过 `_SHARED_TOPOLOGY` 全局变量，**两个 scenario 复用同一份 Topology**。

## 调度评分

样例使用最小 cache-aware 打分：

```text
total_score = cache_hit_score + freshness_score + load_score
```

其中：

```text
cache_hit_score     目标节点已有该函数 warm 缓存时获得高分（10.0）
freshness_score     缓存越新分数越高（1.0 / (1 + last_access_age)）
load_score          节点已放置 Pod 越少分数越高（0.2 / (1 + pod_count)）
```

该公式用于展示机制，后续可以替换为论文第四章中的缓存状态与容量画像协同调度评分。

## 输出文件

运行结束后，结果会保存到：

```text
examples/19_cache_aware_scheduler/outputs/
```

主要文件：

```text
cache_state_snapshot.csv                            # 输入缓存快照
cache_blind/cache_aware_scheduler_summary.csv      # cache_blind 场景摘要
cache_blind/cache_aware_function_summary.csv       # per-function 摘要
cache_blind/cache_aware_request_probe.csv          # 每次 invoke 探针
cache_blind/cache_aware_probe_invocation_join.csv  # probe × invocations 关联
cache_aware/cache_aware_scheduler_summary.csv      # cache_aware 场景摘要
cache_aware/cache_aware_function_summary.csv
cache_aware/cache_aware_request_probe.csv
cache_aware/cache_aware_probe_invocation_join.csv
cache_aware/cache_aware_candidate.csv              # 每个候选节点的评分
cache_aware_scheduler_comparison.csv               # 跨场景对比
cache_aware_scheduler_paper_highlight.csv          # 论文 demo 关键摘要
```

## 关键导出

### 1. `cache_aware_scheduler_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                          value
cache_hit_rate__cache_blind                                      0.000
cache_hit_rate__cache_aware                                      1.000
cache_hit_count__cache_blind                                     0
cache_hit_count__cache_aware                                     10
avg_final_duration__cache_blind                                  1.150
avg_final_duration__cache_aware                                  0.100
total_cold_start_penalty__cache_blind                            10.500
total_cold_start_penalty__cache_aware                            0.000
cache_hit_rate_improvement__cache_aware_over_cache_blind         1.000
cold_start_penalty_reduction__cache_aware_over_cache_blind      1.000
avg_duration_reduction__cache_aware_over_cache_blind             0.913
probe_invocation_duration_match__cache_blind                     1.000
probe_invocation_duration_match__cache_aware                     1.000
```

**关键发现**：
- **cache_hit_rate 提升 100%**（cache_blind 0% → cache_aware 100%）。
- **冷启动惩罚降低 100%**（10.5s → 0.0s）。
- **平均请求耗时降低 91.3%**（1.15s → 0.10s）。
- 论文 demo 一句话核心：**"cache-aware 调度把 10/10 request 全部路由到 warm cache 节点"**。

### 2. `cache_aware/cache_aware_candidate.csv` —— 候选节点评分

每个 (function, candidate_node) 记录 cache_hit / freshness_score / load_score / total_score：

| function | candidate_node | cache_hit | total_score |
|---|---|---|---|
| img-resize | server_0 | True | 10.97 |
| img-resize | server_1 | False | 0.19 |
| img-resize | server_2 | False | 0.19 |
| img-resize | server_3 | False | 0.19 |
| fft | server_0 | False | 0.20 |
| fft | server_1 | True | 10.61 |
| ... | ... | ... | ... |

cache_aware 选 total_score 最高的节点。

### 3. probe×invocation join —— 论文 demo 关键证据

按 (function_name, node_name, request_id) 关联 probe 和 invocations：

| function | node | probe_simtime | probe_final_duration | inv_t_start | inv_t_exec | duration_match |
|---|---|---|---|---|---|---|
| img-resize | server_0 | 12.00 | 0.10 | 12.00 | 0.10 | True |
| fft | server_1 | 12.10 | 0.10 | 12.10 | 0.10 | True |
| ... | ... | ... | ... | ... | ... | ... |

每个 scenario 10 行，**`duration_match` 和 `simtime_match` 全部 True**。

### 4. 论文 demo 关键图 —— cache_blind vs cache_aware 对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/19_cache_aware_scheduler/outputs/cache_aware_scheduler_comparison.csv")
fig, ax = plt.subplots(figsize=(8, 4))
x = range(len(df))
width = 0.35
ax.bar([i - width/2 for i in x], df["total_cold_start_penalty"], width,
       label="total_cold_start_penalty (s)", color="steelblue")
ax.bar([i + width/2 for i in x], df["avg_final_duration"], width,
       label="avg_final_duration (s)", color="darkorange")
ax.set_xticks(list(x))
ax.set_xticklabels(df["scenario"], rotation=10, ha="right")
ax.set_ylabel("value")
ax.set_title("Cache-aware vs cache-blind scheduler")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**15 个核心不变量**应同时满足（15/15 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `comparison` 行数 = 2 | self-check |
| 2-3 | 两个 scenario `request_events` = 10 | self-check |
| 4 | cache_aware 命中率 >= cache_blind（论文核心结论） | self-check（1.0 >= 0.0） |
| 5 | cache_aware 冷启动惩罚 <= cache_blind | self-check（0.0 <= 10.5） |
| 6-7 | probe×invocation duration_match 100% | self-check（10/10 + 10/10） |
| 8-9 | paper highlight 跟 comparison 一致 | self-check |
| 10 | cache snapshot node_name 都是 server_* | self-check |
| 11 | cache_aware 选过的节点都在 server_* 范围 | self-check |
| 12 | cache_aware 选过的节点 ∩ cache 节点 = cache 节点（**核心**） | self-check |
| 13 | paper highlight 提升值跟 comparison 一致 | self-check |
| 14-15 | 两个 scenario 都在 4-server topology 范围内 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cache_aware_scheduler self-check ===
INFO:analysis:  [PASS] comparison_row_count : comparison rows=2, expected=2
INFO:analysis:  [PASS] request_events__cache_blind : request_events=10, expected=10
INFO:analysis:  [PASS] request_events__cache_aware : request_events=10, expected=10
INFO:analysis:  [PASS] cache_aware_beats_cache_blind_hit_rate : cache_aware=1.0000, cache_blind=0.0000
INFO:analysis:  [PASS] cache_aware_below_cache_blind_cold_penalty : cache_aware=0.0000, cache_blind=10.5000
INFO:analysis:  [PASS] probe_invocation_duration_match__cache_blind : duration_match=10/10
INFO:analysis:  [PASS] probe_invocation_duration_match__cache_aware : duration_match=10/10
INFO:analysis:  [PASS] paper_highlight_cache_hit_rate__cache_blind : 0.000000=0.000000
INFO:analysis:  [PASS] paper_highlight_cache_hit_rate__cache_aware : 1.000000=1.000000
INFO:analysis:  [PASS] cache_snapshot_node_names_valid : cached nodes=['server_0', 'server_1', 'server_2']
INFO:analysis:  [PASS] cache_aware_selected_nodes_in_server_range : ['server_0', 'server_1', 'server_2']
INFO:analysis:  [PASS] cache_aware_chooses_cached_nodes : intersection=['server_0', 'server_1', 'server_2']
INFO:analysis:  [PASS] paper_highlight_improvement_consistency : 1.000000=1.000000
INFO:analysis:  [PASS] selected_nodes_in_4_server_topology__cache_blind : OK
INFO:analysis:  [PASS] selected_nodes_in_4_server_topology__cache_aware : OK
INFO:analysis:=== 15 passed, 0 warned, 0 failed ===
```

## 目录结构

```text
19_cache_aware_scheduler/
├── inputs/                              # cache snapshot + workload
│   ├── cache_state_snapshot.csv
│   └── workload.csv
├── outputs/                             # 运行输出
│   ├── cache_aware/                     # cache_aware 场景
│   ├── cache_blind/                     # cache_blind 场景
│   ├── cache_aware_scheduler_comparison.csv
│   ├── cache_aware_scheduler_paper_highlight.csv
│   └── cache_state_snapshot.csv
├── __init__.py
├── analysis.py                          # 摘要 + probe×invocation join + paper highlight + self-check
├── benchmark.py                         # CacheAwareSchedulerBenchmark
├── cache_state.py                       # CacheEntry + CacheStateIndex + load_cache_state
├── main.py                              # 入口（含 _SHARED_TOPOLOGY 最小 4-server 拓扑）
├── scheduler.py                         # CacheAwareScheduler + CacheBlindScheduler
├── simulator.py                         # CacheAwareFunctionSimulator（含 simtime 字段）
└── workload.py                          # SchedulerRequest + load_workload
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取缓存状态快照；
2. 读取请求负载；
3. 构造**最小 4-server 拓扑**（避免 ether.scenarios.urbansensing 状态污染）；
4. 运行 cache_blind 场景；
5. 运行 cache_aware 场景；
6. 导出跨场景对比 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/cache_state_snapshot.csv`

节点级函数 warm 缓存快照。

默认 4 个 (function, node) 缓存项。

### `inputs/workload.csv`

请求负载文件。

默认 10 个 request（arrival_time 0.0 → 1.8）。

### `cache_state.py`

缓存状态索引文件。

提供 `CacheStateIndex`，用于按函数和节点查询缓存命中状态。

### `scheduler.py`

调度器文件。

- `CacheBlindScheduler`：轮转选择 server 节点（cache_hit 字段恒为 False）；
- `CacheAwareScheduler`：按 cache_hit + freshness + load 打分选最高分节点。

### `benchmark.py`

Benchmark 文件。

为每个函数创建独立镜像名（避免 faas-sim 按 image 统计副本时把多函数合并），按 scale_min=1, scale_max=1 部署。

### `simulator.py`

函数生命周期模拟器文件。

在 invoke 阶段根据调度节点是否存在目标函数 warm 缓存，记录 cache hit / miss 和冷启动惩罚。**probe 包含 simtime 字段**（用于跟 invocations join）。

### `analysis.py`

指标导出 + probe×invocation join + 论文 demo 关键摘要 + 数据自洽段文件。

- 12 个 faas-sim / cache_aware 原生 metric 提取；
- `build_scenario_summary`：per-scenario 摘要（cache_hit_rate, total_cold_start_penalty 等）；
- `build_function_summary`：per-function 摘要；
- `build_probe_invocation_join`：probe × invocations 关联（论文 demo 关键证据）；
- `build_paper_highlight`：跨场景对比 + 提升倍数；
- 数据自洽段：15 个不变量。

### `outputs/`

运行结果输出目录。

两个 scenario 子目录 + 跨场景对比 + paper highlight。
