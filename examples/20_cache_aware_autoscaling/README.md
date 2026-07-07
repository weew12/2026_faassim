# 20_cache_aware_autoscaling：缓存状态感知扩缩容样例

本样例用于演示缓存状态感知扩缩容的最小实验闭环。核心思想是同时计算缓存需求副本数 `R_cache` 和负载需求副本数 `R_load`，并组合得到最终目标副本数：

```text
R_desired = max(R_cache, R_load)
```

**本样例不跑 faas-sim Simulation，是时间序列驱动的扩缩容决策实验**。

## 运行方式

将 `20_cache_aware_autoscaling/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/20_cache_aware_autoscaling/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何从函数状态时间序列读取负载、冷启动代价、warm 副本和当前副本数；
2. 如何计算缓存需求副本数 `R_cache`；
3. 如何计算负载需求副本数 `R_load`；
4. 如何组合得到 `R_desired = max(R_cache, R_load)`；
5. 如何根据 `R_desired` 输出 scale-out、scale-in、protect、prewarm 和 observe 动作；
6. 如何在缓存容量预算下筛选需要保护或预热的函数；
7. **如何做 decision×control_plan 关联验证**：每个 decision 都对应一个 plan，且 action / target_replicas / safe_to_execute 语义一致（论文 demo 关键证据）；
8. **如何做数据自洽段**（9 个不变量）。

## R_cache 计算

样例先计算冷启动收益：

```text
cold_benefit = avg_cold_start * (0.6 * n_req + 1.5 * cold_miss_count + 2.0 * request_rate)
```

资源代价为：

```text
resource_cost = memory_units * resource_weight
```

缓存效用为：

```text
cache_utility = cold_benefit / resource_cost
```

当函数存在正在执行请求，或缓存效用超过阈值时，`R_cache` 至少为 1；当函数长期空闲且无请求时，`R_cache` 为 0。

## R_load 计算

负载需求副本数使用最小容量公式：

```text
R_load = ceil(request_rate / (replica_capacity_rps * target_utilization))
```

其中 `replica_capacity_rps` 表示单副本承载能力，`target_utilization` 表示目标利用率。

## R_desired 组合

最终目标副本数为：

```text
R_desired = max(R_cache, R_load)
```

这样可以避免两类错误：

```text
只看负载：低负载但高冷启动函数会被过早缩到 0
只看缓存：高负载函数可能无法及时扩容
```

## 输入文件

函数状态时间序列输入文件：

```text
inputs/function_state_timeseries.csv
```

字段包括：

```text
time
function_name
current_replicas
warm_replicas
n_req
request_rate
avg_response_time
avg_cold_start
cold_miss_count
memory_units
replica_capacity_rps
in_flight_requests
last_seen_age
```

默认输入：5 个时间点 × 4 个函数 = 20 个 state，cache_budget=5 unit。

## 输出文件

运行结束后，结果会保存到：

```text
examples/20_cache_aware_autoscaling/outputs/
```

主要文件：

```text
cache_aware_autoscaling_decision.csv           # 每个 state 的完整决策明细
cache_aware_autoscaling_control_plan.csv       # 每个 decision 对应的 control_plan
cache_aware_autoscaling_action_summary.csv      # per-(action, reason) 摘要
cache_aware_autoscaling_function_summary.csv    # per-function 摘要
cache_aware_autoscaling_time_summary.csv        # per-time 总副本需求摘要
cache_aware_autoscaling_decision_plan_join.csv  # decision × control_plan 关联
cache_aware_autoscaling_paper_highlight.csv    # 论文 demo 关键摘要
```

## 关键导出

### 1. `cache_aware_autoscaling_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                            value
action_count__scale_out                           5
action_count__scale_in                            6
action_count__protect                             8
action_count__prewarm                             0
action_count__observe                             1
r_load_dominant_events                            5
r_cache_only_events                               0
r_both_active_events                              14
r_neither_active_events                           1
r_load_dominant_ratio                             0.250
cache_budget_used                                 4
cache_budget_total                                5
cache_budget_utilization                           0.800
r_cache_rejected_by_budget                        4
decision_plan_consistency                         1.000
per_time_total_r_cache__0.0                       3
per_time_total_r_cache__1.0                       4
per_time_total_r_cache__2.0                       3
per_time_total_r_cache__3.0                       3
per_time_total_r_cache__4.0                       2
per_time_total_r_load__1.0                        6
per_time_total_r_load__2.0                        8
per_time_total_r_desired__1.0                     6
per_time_total_r_desired__2.0                     8
```

**关键发现**：
- **5 个动作分布**：scale_out=5, scale_in=6, protect=8, prewarm=0, observe=1。
- **R_cache vs R_load 主导分析**：14/20 decision 是 `r_both_active`（R_cache > 0 且 R_load > 0），5/20 是 `r_load_dominant`（R_load > R_cache），0/20 是 `r_cache_only`（R_cache > 0 且 R_load == 0）—— **R_cache 单独主导的事件数为 0**，说明 cache 状态通常和 load 一起保护（多发生在 in_flight 期间）。
- **R_load 主导 25%**：5/20 decision R_load 单独放大副本（峰值在 time=1, 2）。
- **cache_budget 80% 利用**：4/5 unit 用了，**1 unit 空着**。
- **4 个 R_cache 被 budget 拒绝**（video-transcode 长期 idle 还要 3 unit，被 budget 限）。
- **time=1/2 的 R_load 主导**：total_r_load=6/8，但 total_r_cache=4/3，**R_load 触发了更多扩容**。

### 2. `cache_aware_autoscaling_decision_plan_join.csv` —— decision × control_plan 关联（论文 demo 关键证据）

按 (time, function_name) 关联 decision 和 control_plan：

| time | function | action | plan_action | target_r | r_desired | safe | match |
|---|---|---|---|---|---|---|---|
| 0.0 | fft | scale_out | scale_out | 1 | 1 | True | True |
| 0.0 | img-resize | protect | protect | 1 | 1 | True | True |
| 0.0 | json-parse | protect | protect | 1 | 1 | True | True |
| 0.0 | video-transcode | scale_in | scale_in | 0 | 0 | True | True |
| ... | ... | ... | ... | ... | ... | ... | ... |

预期 20 行，**`match` 全部 True**。

**验证规则**：
- `decision.action` == `plan.control_action`
- `plan.target_replicas` == `decision.r_desired`
- `scale_in` 且 `in_flight_requests > 0` 时 `safe_to_execute=False`
- `r_desired == current_replicas` 时 `executor_required=False`

### 3. 论文 demo 关键图 —— R_cache vs R_load 时间序列

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/20_cache_aware_autoscaling/outputs/cache_aware_autoscaling_decision.csv")
agg = df.groupby("time").agg(
    total_r_cache=("r_cache", "sum"),
    total_r_load=("r_load", "sum"),
    total_r_desired=("r_desired", "sum"),
).reset_index()

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(agg["time"], agg["total_r_cache"], "o-", label="R_cache", color="steelblue")
ax.plot(agg["time"], agg["total_r_load"], "s-", label="R_load", color="darkorange")
ax.plot(agg["time"], agg["total_r_desired"], "^--", label="R_desired", color="gray")
ax.set_xlabel("simtime")
ax.set_ylabel("replicas")
ax.set_title("Cache-aware autoscaling: R_cache vs R_load")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**9 个核心不变量**应同时满足（9/9 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `decision` 行数 == `control_plan` 行数（20=20） | self-check |
| 2 | `decision` 行数 > 0 | self-check |
| 3 | `r_desired == max(r_cache, r_load)`（全部 20 个 decision） | self-check |
| 4 | per-time cache_budget 不超（max 4 ≤ 5） | self-check |
| 5 | decision×plan join 100% match | self-check（20/20） |
| 6 | action 字段只取 5 类有效值 | self-check |
| 7 | r_desired 在 [min_replicas, max_replicas] 范围内（[0, 4] ⊆ [0, 5]） | self-check |
| 8 | paper highlight 5 类 action_count 加总 = 20 | self-check |
| 9 | paper highlight `decision_plan_consistency` = 1.0 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cache_aware_autoscaling self-check ===
INFO:analysis:  [PASS] decision_plan_count_match : decisions=20, plans=20
INFO:analysis:  [PASS] decision_count : decisions=20
INFO:analysis:  [PASS] r_desired_equals_max_r_cache_r_load : all 20 decisions satisfy r_desired=max(r_cache, r_load)
INFO:analysis:  [PASS] cache_budget_within_limit : per-time violations=0, max selected memory per time=4, budget=5
INFO:analysis:  [PASS] decision_plan_join_match : matched=20/20
INFO:analysis:  [PASS] action_values_valid : observed=['observe', 'protect', 'scale_in', 'scale_out']
INFO:analysis:  [PASS] r_desired_in_clamp_range : r_desired range=[0, 4], expected subset of [0, 5]
INFO:analysis:  [PASS] paper_highlight_action_count_sum : sum of action_count metrics=20, decisions=20
INFO:analysis:  [PASS] paper_highlight_decision_plan_consistency : decision_plan_consistency=1.0000
INFO:analysis:=== 9 passed, 0 failed ===
```

## 目录结构

```text
20_cache_aware_autoscaling/
├── inputs/                              # 函数状态时间序列
│   └── function_state_timeseries.csv
├── outputs/                             # 运行输出
├── __init__.py
├── analysis.py                          # 摘要 + decision×plan join + paper highlight + self-check
├── autoscaler.py                        # CacheAwareAutoscaler（R_cache + R_load + 预算 + 控制计划）
├── loader.py                            # FunctionState + load_function_states
├── main.py                              # 入口
└── models.py                            # FunctionState / AutoscalingConfig / Decision / ControlPlan
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数状态时间序列；
2. 创建扩缩容配置（`cache_capacity_budget_units=5`）；
3. 调用 CacheAwareAutoscaler 生成决策；
4. 生成控制计划；
5. 导出结果文件 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/function_state_timeseries.csv`

函数状态时间序列输入文件。

默认 5 个时间点 × 4 个函数 = 20 个 state。

### `loader.py`

输入读取文件。

从 CSV 读取函数状态时间序列，按 (time, function_name) 排序。

### `models.py`

数据结构定义文件。

定义 `FunctionState` / `AutoscalingConfig` / `AutoscalingDecision` / `ControlPlan`。

### `autoscaler.py`

扩缩容核心逻辑文件。

提供 `CacheAwareAutoscaler`：

- `_cold_benefit` / `_resource_cost` / `_r_cache_raw` / `_r_load_raw`：单 state 评分；
- `_clamp_replicas`：限制在 [min, max] 范围内；
- `_classify_action`：根据 r_desired 和 current_replicas 生成 5 类动作；
- `_apply_cache_budget`：贪心选 r_cache 候选（按 cache_utility 降序），剩余的 r_cache 被削减为 0 但保留 r_load；
- `build_control_plans`：decision → control_plan（含 executor_required / safe_to_execute）。

### `analysis.py`

结果导出 + decision×plan 关联 + 论文 demo 关键摘要 + 数据自洽段文件。

- `build_action_summary`：per-(action, reason) 摘要；
- `build_function_summary`：per-function 摘要（含 4 类动作计数）；
- `build_time_summary`：per-time 总副本需求摘要；
- `build_decision_plan_join`：decision × control_plan 关联（论文 demo 关键证据）；
- `build_paper_highlight`：动作分布 + R_cache vs R_load 主导分析 + capacity 利用 + decision_plan_consistency + per-time 总副本；
- 数据自洽段：9 个不变量。

### `outputs/`

运行结果输出目录。

包含 7 个 CSV（decision / control_plan / 3 summary / decision_plan_join / paper_highlight）。
