# 18_cache_decision：冷启动感知缓存决策样例

本样例用于演示函数实例缓存决策过程。它基于函数画像快照计算冷启动收益、资源代价和缓存效用，并输出 keep_warm、prewarm_candidate、eviction_candidate 和 observe 四类决策结果。

**本样例不跑 faas-sim Simulation，是静态画像驱动的缓存决策实验**。

## 运行方式

将 `18_cache_decision/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/18_cache_decision/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何从函数画像快照中读取请求量、冷启动代价、资源占用和副本状态；
2. 如何计算冷启动收益、资源代价和缓存效用；
3. 如何生成 `keep_warm`、`prewarm_candidate`、`eviction_candidate` 和 `observe` 四类决策；
4. 如何在容量预算下选择需要保护或预热的函数；
5. 如何把缓存决策转换为控制建议；
6. **如何做 decision×hint 关联验证**：每个决策都有正确的 control_action 和 safe_to_execute 语义（论文 demo 关键证据）；
7. **如何做数据自洽段**（10 个不变量）。

## 决策类型

样例输出四类核心决策：

```text
keep_warm            当前已有 warm 副本，且冷启动收益较高，应继续保护
prewarm_candidate    当前没有副本，但冷启动收益较高，可作为预热候选
eviction_candidate   当前有副本，但长期空闲或效用较低，可作为释放候选
observe              暂不动作，仅观察
```

## 最小效用公式

样例使用如下最小公式计算冷启动收益：

```text
cold_benefit = avg_cold_start * (0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate)
```

资源代价为：

```text
resource_cost = memory_units * resource_weight
```

缓存效用为：

```text
utility_score = cold_benefit / resource_cost
```

这些公式用于样例演示，后续可以替换为论文中的 `R_cache`、在线画像状态或更完整的效用模型。

## 输入文件

函数画像快照输入文件：

```text
inputs/function_profile_snapshot.csv
```

字段为：

```text
function_name
current_replicas
warm_replicas
n_req
cold_miss_count
avg_cold_start
warm_duration
memory_units
last_seen_age
in_flight_requests
request_rate
```

默认快照包含 7 个函数，capacity_budget=4 unit。

## 输出文件

运行结束后，结果会保存到：

```text
examples/18_cache_decision/outputs/
```

主要文件：

```text
cache_decision_detail.csv            # 每个函数的完整决策明细
cache_decision_summary.csv           # per-(decision, capacity_status) 摘要
cache_decision_rank.csv              # keep_warm / prewarm_candidate 按 priority 排序
cache_eviction_candidate.csv         # eviction_candidate 函数列表
cache_control_hint.csv               # 每个函数对应的 control_action
cache_decision_hint_join.csv         # decision × hint 关联（论文 demo 关键证据）
cache_decision_paper_highlight.csv   # 论文 demo 关键摘要
```

## 关键导出

### 1. `cache_decision_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                     value
decision_count__keep_warm                  3
decision_count__prewarm_candidate          2
decision_count__eviction_candidate         1
decision_count__observe                    1
top_utility_rank_1__img-resize             57.87
top_utility_rank_2__fft                    25.43
top_utility_rank_3__ml-infer               20.58
capacity_budget_used                       4
capacity_budget_total                      4
capacity_budget_utilization                1.000
decision_hint_consistency                  1.000
decision_hint_matched                      7
decision_hint_total                        7
eviction_reason__thumbnail                 idle_warm_instance
```

**关键发现**：
- **utility_score top-3**：img-resize (57.87) > fft (25.43) > ml-infer (20.58) —— 这三个函数最值得保护/预热。
- **capacity_budget 100% 利用**：3 个 keep_warm 函数（report-gen=2 + img-resize=1 + json-parse=1）正好用满 4 unit 预算。
- **decision_hint_consistency = 1.0**：所有 7 个 decision 都正确映射到对应的 control_action 和 safe_to_execute。
- **eviction_candidate**：thumbnail（last_seen_age=12，n_req=0）正确识别为释放候选。

### 2. `cache_decision_hint_join.csv` —— decision × control_hint 关联（论文 demo 关键证据）

按 function_name 关联 decision 和 control_hint：

| function_name | decision | hint_action | safe_to_execute | match | detail |
|---|---|---|---|---|---|
| report-gen | keep_warm | protect_current_replica | True | True | ok |
| img-resize | keep_warm | protect_current_replica | True | True | ok |
| fft | prewarm_candidate | scale_to_one_if_selected | False | True | ok |
| ml-infer | prewarm_candidate | scale_to_one_if_selected | False | True | ok |
| json-parse | keep_warm | protect_current_replica | True | True | ok |
| video-transcode | observe | observe | True | True | ok |
| thumbnail | eviction_candidate | scale_to_zero_candidate | True | True | ok |

预期 7 行，**`match` 全部 True**。

**验证规则**：
- `keep_warm` → `control_action="protect_current_replica"` 且 `safe_to_execute=True`
- `prewarm_candidate` → `control_action="scale_to_one_if_selected"`，仅当 `selected_by_budget=True` 时 `safe_to_execute=True`
- `eviction_candidate` → `control_action="scale_to_zero_candidate"`，当 `in_flight_requests=0` 时 `safe_to_execute=True`
- `observe` → `control_action="observe"` 且 `safe_to_execute=True`

### 3. 论文 demo 关键图 —— 决策分布

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/18_cache_decision/outputs/cache_decision_paper_highlight.csv")
df_dec = df[df.metric.str.startswith("decision_count__")].copy()
df_dec["decision"] = df_dec.metric.str.replace("decision_count__", "")

fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(df_dec["decision"], df_dec["value"].astype(int),
       color=["steelblue", "darkorange", "lightcoral", "gray"])
ax.set_ylabel("function count")
ax.set_title("Cache decision distribution")
for i, v in enumerate(df_dec["value"].astype(int)):
    ax.text(i, v + 0.05, str(v), ha="center")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**10 个核心不变量**应同时满足（10/10 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `decision` 行数 = 7（profile 数量） | self-check |
| 2 | `hint` 行数 = decision 行数 | self-check |
| 3 | `decision_hint_join` 全部 match | self-check（7/7） |
| 4 | decision 字段只取 4 类有效值 | self-check |
| 5 | 选中 memory ≤ capacity_budget | self-check（4 ≤ 4） |
| 6 | 所有 keep_warm 都被 budget 选中 | self-check |
| 7 | eviction_candidate 都不带 in_flight > 0 | self-check |
| 8 | keep_warm 贪心用满 budget | self-check（4/4） |
| 9 | paper highlight 4 类 decision_count 加总 = 7 | self-check |
| 10 | paper highlight `decision_hint_consistency` = 1.0 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cache_decision self-check ===
INFO:analysis:  [PASS] decision_count : decision rows=7
INFO:analysis:  [PASS] hint_count : hint rows=7, decision rows=7
INFO:analysis:  [PASS] decision_hint_join_match : matched=7/7
INFO:analysis:  [PASS] decision_values_valid : observed decisions=[eviction_candidate, keep_warm, observe, prewarm_candidate]
INFO:analysis:  [PASS] capacity_budget_within_limit : selected memory=4, capacity_budget=4
INFO:analysis:  [PASS] keep_warm_all_selected_by_budget : all keep_warm selected_by_budget: True
INFO:analysis:  [PASS] eviction_candidate_no_in_flight : eviction with in_flight>0: 0
INFO:analysis:  [PASS] keep_warm_budget_greedy : selected keep_warm memory=4, total keep_warm memory=4, capacity_budget=4
INFO:analysis:  [PASS] paper_highlight_decision_count_sum : sum of decision_count metrics=7, profiles=7
INFO:analysis:  [PASS] paper_highlight_decision_hint_consistency : decision_hint_consistency=1.0000
INFO:analysis:=== 10 passed, 0 failed ===
```

## 目录结构

```text
18_cache_decision/
├── inputs/                              # 函数画像快照
│   └── function_profile_snapshot.csv
├── outputs/                             # 运行输出
├── __init__.py
├── advisor.py                           # CacheDecisionAdvisor（评分+分类+capacity 选择）
├── analysis.py                          # 摘要 + decision×hint join + paper highlight + self-check
├── decision_model.py                    # CacheDecisionConfig / CacheDecision / ControlHint
├── main.py                              # 入口
└── profiles.py                          # FunctionProfile + load_profiles
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数画像快照；
2. 创建缓存决策配置（`capacity_budget_units=4`）；
3. 调用 Advisor 生成缓存决策；
4. 生成控制建议；
5. 导出结果文件 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/function_profile_snapshot.csv`

函数画像快照输入文件。

默认 7 个函数（img-resize / json-parse / fft / video-transcode / ml-infer / thumbnail / report-gen）。

### `profiles.py`

画像读取文件。

定义 `FunctionProfile`，并提供 CSV 读取函数。

### `decision_model.py`

决策数据结构文件。

定义 `CacheDecisionConfig` / `CacheDecision` / `ControlHint`。

### `advisor.py`

缓存决策核心文件。

提供 `CacheDecisionAdvisor`：

- `_cold_benefit` / `_resource_cost` / `_classify`：单函数评分 + 分类；
- `_apply_capacity_budget`：贪心选 keep_warm / prewarm_candidate；
- `build_control_hints`：决策转 control_hint。

### `analysis.py`

结果导出 + decision×hint 关联 + 论文 demo 关键摘要 + 数据自洽段文件。

- `build_decision_summary`：per-(decision, capacity_status) 摘要；
- `build_rank_table`：keep_warm / prewarm_candidate 按 priority 排序；
- `build_eviction_table`：eviction_candidate 函数列表；
- `build_decision_hint_join`：decision × control_hint 关联（论文 demo 关键证据）；
- `build_paper_highlight`：决策分布 + utility top-3 + capacity budget 利用 + consistency；
- 数据自洽段：10 个不变量。

### `outputs/`

运行结果输出目录。

包含 7 个 CSV（detail / summary / rank / eviction / control_hint / decision_hint_join / paper_highlight）。
