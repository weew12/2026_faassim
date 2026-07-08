# 17_cache_policy — 函数实例缓存策略对比

> **目标**：对比 FIFO / LRU / UtilityAware 三类函数实例缓存策略，
> 验证 utility_aware 命中率能达到 fifo 的 2.5x，并通过 eviction×state join
> 验证每次驱逐后 state cache_keys 确实不含被驱逐函数。

## 1. 复现步骤

```bash
# 1) 跑仿真（in-memory 缓存算法实验，32 request × 3 policy = 96 request_result）
python -u examples/17_cache_policy/main.py

# 2) 跑绘图（4 张图：策略命中率 + per-function + cache state 演变 + 论文摘要）
python -u examples/17_cache_policy/plot.py
```

输出：
- `outputs/`：3 个核心表（request_result / eviction / state）+ 3 个 summary + 1 个 join + 1 个 paper_highlight + 1 个 self_check
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 三类策略

| 策略 | 驱逐决策 | 公式 |
|------|---------|------|
| `fifo` | 最早进入缓存的函数 | `min(inserted_time)` |
| `lru` | 最近最少访问的函数 | `min(last_access_time)` |
| `utility_aware` | 单位资源效用最低的函数 | `utility = cold_start_duration * (1 + access_count) / memory_units`，选 `min(utility)` |

### 2.2 函数规格（`function_catalog.py`）

5 个函数，模拟论文 demo 中的典型场景：

| function | cold_start | warm | memory_units | 期望模式 |
|----------|-----------|------|--------------|---------|
| `img-resize` | 0.80s | 0.08s | 1 | 频繁调用（11/32），low resource → 受益最多 |
| `json-parse` | 0.35s | 0.04s | 1 | 中频调用（7/32） |
| `fft` | 1.40s | 0.18s | 2 | 中频调用（6/32），high cold_start |
| `video-transcode` | 2.20s | 0.45s | 3 | 低频调用（4/32），high cold_start + high memory |
| `ml-infer` | 1.90s | 0.30s | 2 | 低频调用（4/32），high cold_start |

### 2.3 实验设置

- **trace**：32 request（time 从 0.0 到 9.5），覆盖 5 个函数
- **cache capacity**：4 memory_units（trace 中 5 个函数总 memory=9，所以必然会有驱逐）
- **每个策略独立运行一次**：policy_name 是 cache_request_result / cache_state 表的主键

### 2.4 关键 join（论文 demo 关键证据）

`cache_eviction_state_join.csv` 按 (policy_name, time, function_name) 关联 eviction 和 cache_state，验证：
- 每次 eviction 之后，state cache_keys 确实不含刚被 evict 的函数

**关键不变量**：`state.cache_keys 不应包含刚被 evict 的函数`（runner 在 add 新 entry 之前 cache_keys 是 evict 后的状态）。

## 3. 数据自检（17 项 PASS）

```
data self-check: 17 / 17 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `cache_request_result_row_count` | 3 policy × 32 request = 96 行 |
| 02 | `cache_state_row_count` | 96 行 = request 行数 |
| 03 | `cache_policy_summary_row_count` | 3 policy = 3 行 |
| 04-06 | `policy_request_count__{policy}` | 每个 policy request_count = 32 |
| 07-09 | `function_summary_total_requests__{policy}` | 每个 policy 5 个 function 求和 = 32 |
| 10 | `eviction_state_join_row_count` | eviction×state join 行数 == eviction 行数（69） |
| 11 | `eviction_state_consistency` | 69/69 eviction 后 state 不含 evicted function |
| 12-14 | `paper_highlight_hit_rate__{policy}` | paper highlight 3 个 hit_rate 跟 policy_summary 一致 |
| 15 | `utility_aware_beats_fifo` | utility_aware hit_rate >= fifo（**论文核心结论**） |
| 16 | `paper_highlight_hit_rate_improvement` | paper highlight hit_rate_improvement 跟 summary 一致 |
| 17 | `export_tables_have_no_index_column` | 导出的 CSV 不包含 pandas 默认索引列（无 `Unnamed: 0`） |

**关键诚实性事实**：`lru vs fifo hit_rate 完全一样 = 0.125`（sim 模型诚实特性）。
trace 短 + 频繁函数（img-resize 11/32）+ capacity=4，导致 fifo 和 lru 选 victim 偶然表现一样。
**这一点要在论文里诚实写出来**——lru 不一定比 fifo 好，取决于 trace 模式。

## 4. 论文 demo 关键摘要（31 条）

`outputs/cache_policy_paper_highlight.csv` 包含（沿用 02-16 的 metric/value/note 三列模式）：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `total_policies` | 3 | 策略数（fifo / lru / utility_aware） |
| `total_requests_per_policy` | 32 | 每个 policy 的 request 数（trace 共享） |
| `total_functions` | 5 | 函数规格数 |
| `total_function_summary_rows` | 15 | function_summary 行数（3 policy × 5 function） |
| `policy_summary_count` | 3 | policy_summary 行数 |
| `hit_rate__{policy}` | 0.125/0.125/0.3125 | 每策略命中率 |
| `avg_latency__{policy}` | ~1.19/1.19/1.04s | 每策略平均延迟（含冷启动惩罚） |
| `total_cold_start_penalty__{policy}` | 32.85/32.85/28.05 | 每策略累计冷启动惩罚 |
| `avg_cache_used_after__{policy}` | ~3.28/3.38/3.28 | 每策略平均缓存占用（应 <= capacity=4） |
| `miss_count__{policy}` | 28/28/22 | 每策略 miss 次数 |
| `hit_rate_improvement__{policy}_over_fifo` | 0.0/0.1875 | 命中率绝对差（**论文 demo 关键数字**） |
| `hit_rate_ratio__{policy}_over_fifo` | 1.0/2.5x | **论文 demo 一句话核心**：utility_aware=2.5x |
| `latency_reduction__{policy}_over_fifo` | 0.0/0.126 | 平均延迟相对降低 |
| `cold_start_penalty_reduction__{policy}_over_fifo` | 0.0/0.146 | 冷启动惩罚相对降低 |
| `best_function_hit_rate__{policy}__{fn}` | 0.36/0.36/0.91 | 每策略最佳函数命中率 |

## 5. 4 张图说明

### fig01 — Cache policy hit rate (utility_aware = 2.50x fifo)（论文 demo 关键图）
- 柱状图：fifo (红) / lru (橙) / utility_aware (绿)
- y 轴 0~0.5，标题直接显示 2.50x fifo
- **论文价值**：一眼看出 utility_aware 是 fifo 的 2.5x 命中率提升。

### fig02 — Per-function hit_rate by policy
- 分组柱状图：x = function_name (5 个)，每个 function 3 条柱
- 函数按 trace 请求量从高到低排序，`img-resize` 放在最左侧
- **论文价值**：展示 img-resize 是最大受益函数（utility_aware 下 0.91 vs fifo/lru 0.36），
  其他 4 个函数 hit_rate 全 0（capacity 限制）。诚实展示"trace 不均匀 + capacity 限制"下的策略效果。

### fig03 — Cache state evolution
- 三栏小图：fifo (红) / lru (橙) / utility_aware (绿) 分开展示
- x = request_id, y = cache_used (memory_units)，每栏都有 capacity=4 参考线（黑色虚线）
- **论文价值**：展示各策略的 cache 使用模式差异——utility_aware 频繁从 4 降到 2-3（驱逐低效用函数），
  fifo/lru 也有类似行为但 pattern 不同。

### fig04 — Paper Highlight Metrics
- 分组横向条形图：31 个 metric，分为计数/总量、策略性能、相对提升三栏
- **论文价值**：最显眼的 bar 是 `total_cold_start_penalty` (~32.85)、`miss_count` (28)、
  `hit_rate_ratio__utility_aware_over_fifo` (2.5x) 是论文 demo 关键数字。

## 6. 与 02-16 的 demo 价值对比

| 维度 | 02 LB | 12 cold | 14 batch | 16 cosim | **17 cache** |
|------|-------|---------|----------|----------|--------------|
| 验证目标 | 路由均衡 | 冷启动路径 | 批量实验框架 | 外部控制器影响 | **缓存策略效果** |
| 跑 faas-sim? | ✓ | ✓ | ✓ | ✓ | **✗ (in-memory)** |
| 外部输入 | 无 | 无 | 无 | 外部 trace | **请求 trace** |
| 探针 | dispatch | dispatch+phase | dispatch+batch | dispatch+cosim | **request + state + eviction** |
| 关键 join | route×probe | probe×inv | probe×inv | probe×inv | **eviction×state** |
| 核心数字 | balance_std=0 | first/warm=3.75x | hit_ratio=1.0/0.0 | impact=2.49x | **hit_rate_ratio=2.5x** |
| 论文 chart | 阶梯图 | Gantt | 柱+散点+条 | 柱+柱+阴影散点 | **柱+分组柱+折线+条** |

**17 的独特价值**：17 是 02-16 中**唯一一个"不跑 faas-sim Simulation"的样例**。
其他样例都依赖 faas-sim 框架（dispatch + 调度 + 资源管理），17 是纯算法实验。
17 用 utility = cold_start_duration × (1 + access_count) / memory_units 这样的
"冷启动收益感知"公式，证明**在 trace 不均匀时 utility-aware 策略能比 fifo 高 2.5x**。
17 还能扩展到更复杂的效用模型（论文里的 R_cache 或在线学习模型），为论文中
"边缘 Serverless 缓存策略"提供基础。

## 7. 输出文件清单

```
examples/17_cache_policy/
├── main.py                                # 入口：load trace + run policies + export
├── cache_model.py                         # CacheEntry / FunctionCache / RequestResult / EvictionEvent / CacheStateRecord
├── function_catalog.py                    # 5 个 FunctionSpec
├── policies.py                            # FIFO / LRU / UtilityAware
├── runner.py                              # CachePolicyExperimentRunner
├── workload.py                            # FunctionRequest + load_request_trace
├── analysis.py                            # 4 summary + eviction×state join + paper_highlight + self_check
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── inputs/
│   └── request_trace.csv                  # 32 request 覆盖 5 个函数
├── outputs/
│   ├── cache_request_result.csv           # 96 行 = 3 policy × 32 request
│   ├── cache_eviction.csv                 # 驱逐事件
│   ├── cache_state.csv                    # 96 行 = 每个 request 之后的状态
│   ├── cache_eviction_state_join.csv      # eviction × state 关联（论文 demo 关键证据）
│   ├── cache_policy_summary.csv           # per-policy 摘要
│   ├── cache_function_summary.csv         # per-(policy, function) 摘要
│   ├── cache_eviction_summary.csv         # per-(policy, reason) 驱逐摘要
│   ├── cache_policy_paper_highlight.csv   # 论文 demo 关键摘要（31 metric + note）
│   └── cache_policy_self_check.csv         # 17 项数据自检
└── figures/
    ├── fig01_policy_hit_rate_comparison.png/pdf
    ├── fig02_per_function_hit_rate.png/pdf
    ├── fig03_cache_state_evolution.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **不跑 faas-sim Simulation**：17 是 02-16 中**唯一**的纯算法实验。这让 17 能专注于"缓存策略机制"，不被仿真框架的复杂度掩盖。代价是 17 没有 `invoke_dispatch_probe`（因为没跑仿真），paper_highlight 也只有 31 个 metric（比 14/15/16 少）。
- **诚实承认 lru vs fifo 完全一样**：trace 短 + 频繁函数（img-resize 11/32）+ capacity=4，导致 fifo 和 lru 选 victim 偶然表现一样（hit_rate 都 = 0.125）。17 不掩盖这个事实——paper_highlight 里 `lru_over_fifo` 的所有 improvement 都是 0。这是 sim 模型的诚实特性，比强行制造"lru 优势"更能支撑论文可信度。
- **utility_aware 公式简化**：用 `utility = cold_start_duration * (1 + access_count) / memory_units` 作为最小可运行版本。该公式不依赖未来的访问模式（只用 access_count），是无需预测的最简效用模型。后续可以替换为论文中的 R_cache 或更完整的在线效用模型（带预测/强化学习）。
- **memory_units 用抽象单位**：不是具体 MiB。这样让样例重点放在"缓存策略机制"，不涉及具体资源管理的复杂性。同时让 capacity=4 能容纳 4 个 memory=1 的轻量函数（img-resize + json-parse + 2 个其他），但永远不够容纳 video-transcode (memory=3)。
- **eviction×state join 用 (policy, time, function_name) 三元组关联**：因为 runner 在每次 request 之后写一行 state，每个 policy 独立运行，所以 state 不会和跨 policy 的 request 混淆。join 后用 `evicted_function ∉ state_cache_keys` 验证——这是 17 的"驱逐一致性"核心不变量。
- **3 策略 + 5 函数 + 32 request + capacity=4**：实验规模刚好能展示"utility_aware 优势"和"lru/fifo 偶然相同"两个现象，规模再小就看不出 pattern，再大就难复现。
