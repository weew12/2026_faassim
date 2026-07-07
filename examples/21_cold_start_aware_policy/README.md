# 21_cold_start_aware_policy：冷启动感知函数实例保活策略样例

本样例用于演示冷启动感知函数实例保活策略。它将函数 warm 实例抽象为有限容量缓存，并比较固定 keep-alive 策略与冷启动感知 keep-alive 策略的差异。

**本样例不跑 faas-sim Simulation，是 trace 驱动的缓存算法实验**（跟 17 同类）。

## 运行方式

将 `21_cold_start_aware_policy/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/21_cold_start_aware_policy/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何把函数 warm 实例保活抽象为有限容量缓存；
2. 如何根据请求 trace 判断 warm hit 和 cold miss；
3. 如何比较固定 keep-alive 和冷启动感知 keep-alive；
4. 如何根据冷启动代价、近期访问频率和资源占用计算保活效用；
5. 如何在容量预算下执行保活、延长、过期和驱逐决策；
6. **如何做 request×decision 关联验证**：每个 request 对应一个 policy_decision，cache_hit ↔ decision 映射正确（论文 demo 关键证据）；
7. **如何做 eviction×state 关联验证**：每次 eviction 之后，state.warm_keys 不应再包含被驱逐函数；
8. **如何做数据自洽段**（13 个不变量）。

## 策略说明

样例包含两类策略：

```text
fixed_keep_alive      固定保活窗口，所有函数请求后保活 2 个时间单位
cold_start_aware      根据冷启动代价、近期访问频率和资源占用动态计算保活窗口
```

冷启动感知策略的最小效用公式为：

```text
utility = cold_start_duration * (1 + recent_rate) / memory_units
```

动态保活窗口为：

```text
keep_alive_window = base_window + 1.2 * cold_start_duration + 2.0 * recent_rate - 0.3 * memory_units
```

该公式用于演示机制，后续可以替换为论文第三章中的缓存收益函数或在线效用模型。

## 输入文件

函数画像位于：

```text
inputs/function_profile.csv
```

字段包括：

```text
function_name
cold_start_duration
warm_duration
memory_units
```

请求 trace 位于：

```text
inputs/request_trace.csv
```

字段包括：

```text
time
function_name
```

默认输入：6 个函数，30 个 request，cache_capacity=4 unit。

## 输出文件

运行结束后，结果会保存到：

```text
examples/21_cold_start_aware_policy/outputs/
```

主要文件：

```text
cold_start_request_result.csv              # 请求级结果（60 行 = 2 policy × 30 request）
cold_start_policy_decision.csv             # 每个 request 对应的 policy_decision
cold_start_eviction.csv                    # 驱逐事件
cold_start_policy_summary.csv              # per-policy 摘要
cold_start_function_summary.csv            # per-(policy, function) 摘要
cold_start_decision_summary.csv            # per-(policy, decision, reason) 摘要
cold_start_request_decision_join.csv       # request × decision 关联（论文 demo 关键证据）
cold_start_eviction_state_join.csv         # eviction × state 关联（论文 demo 关键证据）
cold_start_policy_paper_highlight.csv      # 论文 demo 关键摘要
```

## 关键导出

### 1. `cold_start_policy_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                            value
hit_rate__cold_start_aware                                        0.2333
hit_rate__fixed_keep_alive                                        0.1333
total_cold_start_penalty__cold_start_aware                        26.700
total_cold_start_penalty__fixed_keep_alive                        29.100
avg_keep_alive_window__cold_start_aware                           2.579
avg_keep_alive_window__fixed_keep_alive                           2.000
eviction_count__cold_start_aware                                  22
eviction_count__fixed_keep_alive                                  24
hit_rate_improvement__cold_start_aware_over_fixed_keep_alive      0.1000
hit_rate_ratio__cold_start_aware_over_fixed_keep_alive            1.7500
latency_reduction__cold_start_aware_over_fixed_keep_alive         0.0709
cold_start_penalty_reduction__cold_start_aware_over_fixed_keep_alive  0.0825
avg_keep_alive_window_diff__cold_start_aware_over_fixed_keep_alive   0.579
request_decision_consistency                                      1.0000
request_decision_matched                                          60
request_decision_total                                            60
eviction_state_consistency                                        1.0000
eviction_state_matched                                            46
eviction_state_total                                              46
```

**关键发现**：
- **命中率从 13.33% 提升到 23.33%**（**+10 个百分点，1.75x 倍数**）。
- **冷启动惩罚降低 8.25%**（29.1s → 26.7s）。
- **平均延迟降低 7.09%**（1.128s → 1.048s）。
- **平均 keep_alive_window 提升 0.579**（2.0 → 2.579，cold_start_aware 真的给高频函数更长的保活窗口）。
- 驱逐次数 cold_start_aware 略少（22 vs 24），说明 utility-aware victim 选择更精确。
- **request×decision 100% 一致**（60/60），证明 cache_hit ↔ decision 映射规则正确。
- **eviction×state 100% 一致**（46/46），证明每次 eviction 之后被驱逐函数不在 state.warm_keys 里。

### 2. `cold_start_request_decision_join.csv` —— request × decision 关联（论文 demo 关键证据）

按 (policy_name, request_id) 关联 request 和 policy_decision：

| policy | request_id | cache_hit | decision | expected | match |
|---|---|---|---|---|---|
| cold_start_aware | 1 | False | keep_after_cold_start | keep_after_cold_start | True |
| cold_start_aware | 2 | False | keep_after_cold_start | keep_after_cold_start | True |
| ... | ... | ... | ... | ... | ... |
| cold_start_aware | 5 | True | extend_keep_alive | extend_keep_alive | True |
| ... | ... | ... | ... | ... | ... |

预期 60 行，**`match` 全部 True**。

**验证规则**：
- `cache_hit=True` → `decision="extend_keep_alive"`
- `cache_hit=False` → `decision="keep_after_cold_start"`
- `keep_alive_window` 在 request 和 decision 两边一致

### 3. `cold_start_eviction_state_join.csv` —— eviction × state 关联（论文 demo 关键证据）

按 (policy_name, ev_time) 关联 eviction 和"下一个 decision"：

| policy | evicted_function | next_dec_warm_keys | match |
|---|---|---|---|
| cold_start_aware | fft | img-resize;ml-infer;video-transcode | True |
| cold_start_aware | json-parse | img-resize;ml-infer;video-transcode | True |
| ... | ... | ... | ... |

预期 46 行，**`match` 全部 True**（被驱逐的函数不在后续 decision 的 warm_keys 里）。

### 4. per-function 摘要（论文 demo 关键）

| function | fixed_keep_alive hit_rate | cold_start_aware hit_rate | 提升 |
|---|---|---|---|
| img-resize (高频) | 44.4% | **77.8%** | **+33.3 pp** |
| fft (中频) | 0% | 0% | 0 |
| json-parse (中频) | 0% | 0% | 0 |
| ml-infer (低频) | 0% | 0% | 0 |
| thumbnail (低频) | 0% | 0% | 0 |
| video-transcode (低频) | 0% | 0% | 0 |

**关键发现**：
- `cold_start_aware` 真的把"高频函数"（img-resize）保活更久（hit_rate 44.4% → 77.8%）。
- 其他低频函数 hit_rate 都是 0%（被驱逐后下次访问时已 cold）—— **sim 模型的诚实特性**：
  trace 短（30 request）+ 6 个函数 + capacity=4，低频函数 5 个时间单位内不会重新访问。

### 5. 论文 demo 关键图 —— 策略命中率对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/21_cold_start_aware_policy/outputs/cold_start_policy_summary.csv")
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(df["policy_name"], df["hit_rate"],
       color=["lightcoral", "steelblue"])
ax.set_ylabel("hit_rate")
ax.set_ylim(0, 0.4)
ax.set_title("Cold start aware keep-alive policy hit rate")
for i, v in enumerate(df["hit_rate"]):
    ax.text(i, v + 0.01, f"{v:.3f}", ha="center")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**13 个核心不变量**应同时满足（13/13 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `request_result` 行数 = 60（2 policy × 30 request） | self-check |
| 2 | `policy_decision` 行数 == request 行数 | self-check |
| 3 | `policy_summary` 行数 = 2 | self-check |
| 4-5 | per-policy `request_count` = 30 | self-check |
| 6-7 | per-policy function summary 求和 = 30 | self-check |
| 8 | request×decision join 100% match | self-check（60/60） |
| 9 | eviction×state join 100% match | self-check（46/46） |
| 10-11 | paper highlight 2 个 hit_rate 跟 policy_summary 一致 | self-check |
| 12 | paper highlight `hit_rate_ratio` 跟 summary 一致 | self-check（1.75） |
| 13 | cold_start_aware 命中率 >= fixed_keep_alive（论文核心） | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cold_start_aware_policy self-check ===
INFO:analysis:  [PASS] request_result_row_count : requests=60, expected=60
INFO:analysis:  [PASS] policy_decision_row_count : decisions=60, requests=60
INFO:analysis:  [PASS] policy_summary_row_count : summary rows=2, expected=2
INFO:analysis:  [PASS] policy_request_count__cold_start_aware : request_count=30, expected=30
INFO:analysis:  [PASS] policy_request_count__fixed_keep_alive : request_count=30, expected=30
INFO:analysis:  [PASS] function_summary_total_requests__cold_start_aware : sum=30
INFO:analysis:  [PASS] function_summary_total_requests__fixed_keep_alive : sum=30
INFO:analysis:  [PASS] request_decision_consistency : matched=60/60
INFO:analysis:  [PASS] eviction_state_consistency : matched=46/46
INFO:analysis:  [PASS] paper_highlight_hit_rate__cold_start_aware : 0.233333
INFO:analysis:  [PASS] paper_highlight_hit_rate__fixed_keep_alive : 0.133333
INFO:analysis:  [PASS] paper_highlight_hit_rate_ratio : 1.750000
INFO:analysis:  [PASS] cold_start_aware_beats_fixed_keep_alive : 0.2333 >= 0.1333
INFO:analysis:=== 13 passed, 0 failed ===
```

## 目录结构

```text
21_cold_start_aware_policy/
├── inputs/                              # 请求 trace + 函数画像
│   ├── function_profile.csv
│   └── request_trace.csv
├── outputs/                             # 运行输出
├── __init__.py
├── analysis.py                          # 摘要 + request×decision + eviction×state + paper + self-check
├── loader.py                            # FunctionProfile + RequestEvent
├── main.py                              # 入口
├── models.py                            # 数据结构
├── policies.py                          # FixedKeepAlivePolicy + ColdStartAwarePolicy
└── runner.py                            # ColdStartAwarePolicyRunner
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数画像；
2. 读取请求 trace；
3. 创建固定 keep-alive 和冷启动感知 keep-alive 策略（`capacity_units=4`）；
4. 运行策略实验；
5. 导出对比结果 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/function_profile.csv`

函数画像输入文件。

默认 6 个函数（img-resize / json-parse / fft / video-transcode / ml-infer / thumbnail）。

### `inputs/request_trace.csv`

请求 trace 输入文件。

默认 30 个 request（time 从 0.0 到 9.5）。

### `models.py`

数据结构定义文件。

定义 `FunctionProfile` / `RequestEvent` / `WarmEntry` / `RequestResult` / `PolicyDecision` / `EvictionEvent`。

### `loader.py`

输入读取文件。

读取函数画像和请求 trace。

### `policies.py`

策略实现文件。

- `FixedKeepAlivePolicy`：固定保活窗口（2.0s），victim 选择最早 expire；
- `ColdStartAwarePolicy`：动态保活窗口（0.5~6.0s），victim 选择 utility 最低。

### `runner.py`

实验执行器文件。

将请求 trace 输入到不同策略，收集 request_results / policy_decisions / evictions。

### `analysis.py`

结果导出 + request×decision 关联 + eviction×state 关联 + 论文 demo 关键摘要 + 数据自洽段文件。

- 4 个原始 summary（policy / function / decision / eviction）；
- 2 个 join 验证（request×decision / eviction×state）；
- paper highlight：策略相对提升 + consistency；
- 数据自洽段：13 个不变量。

### `outputs/`

运行结果输出目录。

包含 9 个 CSV（3 个原始 + 3 个 summary + 2 个 join + 1 个 paper highlight）。
