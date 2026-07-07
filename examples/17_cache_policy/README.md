# 17_cache_policy：函数实例缓存策略样例

本样例用于演示函数实例缓存策略的最小实验闭环。它将函数副本是否保持 warm 抽象为缓存状态，并根据请求 trace、冷启动代价和资源占用比较不同缓存策略的效果。

**本样例不跑 faas-sim Simulation**，是 in-memory 缓存算法实验。

## 运行方式

将 `17_cache_policy/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/17_cache_policy/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何把函数实例保持 warm 抽象为缓存问题；
2. 如何根据请求 trace 判断 warm hit 和 cold miss；
3. 如何建模函数冷启动代价和缓存资源占用；
4. 如何实现 FIFO、LRU 和 Utility-aware 三类缓存策略；
5. 如何记录请求级延迟、冷启动惩罚、驱逐事件和缓存状态；
6. 如何生成策略级命中率和延迟对比结果；
7. **如何做 eviction×state 关联验证**：每次 eviction 之后，state cache_keys 确实不含被驱逐函数（论文 demo 关键证据）；
8. **如何做数据自洽段**（15 个不变量）。

## 默认策略

样例包含三类策略：

```text
fifo            先进先出，驱逐最早进入缓存的函数
lru             最近最少使用，驱逐最长时间未访问的函数
utility_aware   冷启动收益感知，驱逐单位资源效用最低的函数
```

`utility_aware` 使用的最小效用公式为：

```text
utility = cold_start_duration * (1 + access_count) / memory_units
```

该公式只作为样例中的最小可运行版本，后续可以替换为论文中的 `R_cache` 或更完整的在线效用模型。

## 输入文件

请求 trace 位于：

```text
inputs/request_trace.csv
```

字段为：

```text
time,function_name
```

函数规格在 `function_catalog.py` 中定义，包括：

```text
cold_start_duration
warm_duration
memory_units
description
```

默认 trace 包含 32 个 request，覆盖 5 个函数（img-resize / json-parse / fft / video-transcode / ml-infer），cache capacity = 4 unit。

## 输出文件

运行结束后，结果会保存到：

```text
examples/17_cache_policy/outputs/
```

主要文件：

```text
cache_request_result.csv          # 请求级结果（96 行 = 3 policy × 32 request）
cache_eviction.csv                # 驱逐事件（每 policy 一次驱逐一行）
cache_state.csv                   # 缓存状态（96 行 = 每个 request 之后的状态）
cache_eviction_state_join.csv     # eviction × cache_state 关联（论文 demo 关键证据）
cache_policy_summary.csv          # per-policy 摘要
cache_function_summary.csv        # per-(policy, function) 摘要
cache_eviction_summary.csv        # per-(policy, reason) 驱逐摘要
cache_policy_paper_highlight.csv  # 论文 demo 关键摘要
```

## 关键导出

### 1. `cache_policy_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                              value
hit_rate__fifo                                      0.1250
hit_rate__lru                                       0.1250
hit_rate__utility_aware                             0.3125
total_cold_start_penalty__fifo                      32.85
total_cold_start_penalty__lru                       32.85
total_cold_start_penalty__utility_aware             28.05
hit_rate_improvement__utility_aware_over_fifo       0.1875
hit_rate_ratio__utility_aware_over_fifo             2.5000
latency_reduction__utility_aware_over_fifo          0.1260
cold_start_penalty_reduction__utility_aware_over_fifo  0.1461
best_function_hit_rate__utility_aware__img-resize   0.9091
```

**关键发现**：
- `utility_aware` 命中率 **2.5x** 于 fifo（31.25% vs 12.5%）。
- `utility_aware` 冷启动惩罚降低 **14.61%**。
- `utility_aware` 最佳函数（img-resize）命中率 **90.91%**（10/11）。
- `lru` vs `fifo` 在这个 trace 上 hit_rate 完全一样（**12.5%**）—— 这是 sim 模型的诚实特性：
  trace 短 + 频繁函数（img-resize 11/32）+ capacity=4，导致 fifo 和 lru 选 victim 偶然表现一样。

### 2. `cache_eviction_state_join.csv` —— eviction × cache_state 关联（论文 demo 关键证据）

按 (policy_name, time, function_name) 关联：

| policy | time | function_name | evicted_function | state_cache_keys | eviction_state_match |
|---|---|---|---|---|---|
| fifo | 1.4 | video-transcode | img-resize | fft;video-transcode | True |
| fifo | 1.4 | video-transcode | json-parse | fft;video-transcode | True |
| ... | ... | ... | ... | ... | ... |

预期 69 行，**`eviction_state_match` 全部 True**（被驱逐的函数不应再出现在 state cache_keys 里）。

### 3. 论文 demo 关键图 —— 策略命中率对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/17_cache_policy/outputs/cache_policy_summary.csv")
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(df["policy_name"], df["hit_rate"], color=["lightcoral", "steelblue", "darkorange"])
ax.set_ylabel("hit_rate")
ax.set_ylim(0, 0.5)
ax.set_title("Cache policy hit rate comparison")
for i, v in enumerate(df["hit_rate"]):
    ax.text(i, v + 0.01, f"{v:.3f}", ha="center")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**15 个核心不变量**应同时满足（15/15 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `cache_request_result` 行数 = 96（3 policy × 32 request） | self-check |
| 2 | `cache_state` 行数 = 96 | self-check |
| 3 | `cache_policy_summary` 行数 = 3 | self-check |
| 4-6 | per-policy `request_count` = 32 | self-check |
| 7-9 | per-policy function summary 求和 = 32 | self-check |
| 10 | `eviction_state_match` 100% | self-check（69/69） |
| 11-13 | paper highlight 3 个 hit_rate 跟 policy_summary 一致 | self-check |
| 14 | `utility_aware` 命中率 >= `fifo`（论文核心结论） | self-check |
| 15 | paper highlight `hit_rate_improvement` 跟 summary 一致 | self-check |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== cache_policy self-check ===
INFO:analysis:  [PASS] cache_request_result_row_count : rows=96, expected=96
INFO:analysis:  [PASS] cache_state_row_count : state rows=96, request rows=96
INFO:analysis:  [PASS] cache_policy_summary_row_count : summary rows=3, expected=3
INFO:analysis:  [PASS] policy_request_count__fifo : request_count=32, expected=32
INFO:analysis:  [PASS] policy_request_count__lru : request_count=32, expected=32
INFO:analysis:  [PASS] policy_request_count__utility_aware : request_count=32, expected=32
INFO:analysis:  [PASS] function_summary_total_requests__fifo : sum=32
INFO:analysis:  [PASS] function_summary_total_requests__lru : sum=32
INFO:analysis:  [PASS] function_summary_total_requests__utility_aware : sum=32
INFO:analysis:  [PASS] eviction_state_consistency : matched=69/69
INFO:analysis:  [PASS] paper_highlight_hit_rate__fifo : 0.125000=0.125000
INFO:analysis:  [PASS] paper_highlight_hit_rate__lru : 0.125000=0.125000
INFO:analysis:  [PASS] paper_highlight_hit_rate__utility_aware : 0.312500=0.312500
INFO:analysis:  [PASS] utility_aware_beats_fifo : utility_aware=0.3125, fifo=0.1250
INFO:analysis:  [PASS] paper_highlight_hit_rate_improvement : 0.187500=0.187500
INFO:analysis:=== 15 passed, 0 failed ===
```

## 目录结构

```text
17_cache_policy/
├── inputs/                              # 请求 trace
│   └── request_trace.csv
├── outputs/                             # 运行输出
├── __init__.py
├── analysis.py                          # 摘要 + eviction×state join + paper highlight + self-check
├── cache_model.py                       # CacheEntry / FunctionCache / RequestResult / EvictionEvent
├── function_catalog.py                  # FunctionSpec（5 个函数规格）
├── main.py                              # 入口
├── policies.py                          # FIFO / LRU / UtilityAware
├── runner.py                            # 缓存策略实验执行器
└── workload.py                          # FunctionRequest + load_request_trace
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取请求 trace；
2. 加载函数规格表；
3. 创建缓存策略（`cache_capacity_units=4`）；
4. 运行缓存策略实验；
5. 导出策略对比结果 + 论文 demo 关键摘要 + 数据自洽段。

### `inputs/request_trace.csv`

请求 trace 文件。

默认 32 个 request（time 从 0.0 到 9.5），覆盖 5 个函数。

### `function_catalog.py`

函数规格表文件。

定义 5 个函数的冷启动耗时、热路径耗时和缓存资源占用（`memory_units` 用抽象容量单位，不是具体 MiB）。

### `cache_model.py`

缓存状态模型文件。

定义 `CacheEntry` / `RequestResult` / `EvictionEvent` / `CacheStateRecord` / `FunctionCache`（不决定驱逐对象，只维护状态）。

### `policies.py`

缓存策略文件。

实现 `FIFO` / `LRU` / `UtilityAware` 三类策略。

### `runner.py`

实验执行器文件。

负责把请求 trace 送入每个策略，记录请求级结果、驱逐事件和缓存状态。

### `analysis.py`

结果导出 + eviction×state 关联 + 论文 demo 关键摘要 + 数据自洽段文件。

- `build_policy_summary`：per-policy 摘要（hit_rate、avg_latency、total_cold_start_penalty 等）；
- `build_function_summary`：per-(policy, function) 摘要；
- `build_eviction_summary`：per-(policy, reason) 驱逐摘要；
- `build_eviction_state_join`：eviction × cache_state 关联（论文 demo 关键证据）；
- `build_paper_highlight`：策略相对提升（以 fifo 为 baseline）+ per-policy 关键指标；
- 数据自洽段：15 个不变量。

### `outputs/`

运行结果输出目录。

包含 8 个 CSV（request / eviction / state / 3 个 summary / join / paper highlight）。
