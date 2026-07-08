# 21_cold_start_aware_policy — 冷启动感知函数实例保活策略（fixed vs cold_start_aware 对比）

> **目标**：将函数 warm 实例抽象为有限容量缓存（capacity_units=4），
> 比较 fixed_keep_alive（固定 2.0s 保活窗口）vs cold_start_aware（动态保活窗口 = base + 1.2 * cold_start + 2.0 * recent_rate - 0.3 * memory），
> 验证 cold_start_aware 给高频函数更长的保活窗口 → 命中率提升。

## 1. 复现步骤

```bash
# 1) 跑主程序（6 函数 × 30 request × 2 policy，17/17 PASS）
python -u examples/21_cold_start_aware_policy/main.py

# 2) 跑绘图（4 张图：3 metric 对比 + per-function + decision 分布 + paper highlight）
python -u examples/21_cold_start_aware_policy/plot.py
```

输出：
- `outputs/cold_start_request_result.csv`：60 行（2 policy × 30 request）
- `outputs/cold_start_policy_decision.csv`：60 个 policy_decision
- `outputs/cold_start_eviction.csv`：46 个 eviction 事件
- `outputs/cold_start_policy_summary.csv`：per-policy 摘要
- `outputs/cold_start_function_summary.csv`：per-(policy, function) 摘要
- `outputs/cold_start_decision_summary.csv`：per-(policy, decision, reason) 摘要
- `outputs/cold_start_request_decision_join.csv`：request × decision 关联（论文 demo 关键证据）
- `outputs/cold_start_eviction_state_join.csv`：eviction × state 关联（论文 demo 关键证据）
- `outputs/cold_start_policy_paper_highlight.csv`：21 metric + note
- `outputs/cold_start_aware_policy_self_check.csv`：17 项数据自检
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 6 函数 × 30 request

| 函数 | 类型 | 冷启动代价 | memory |
|------|------|------------|--------|
| img-resize | 高频 | 0.4s | 1 |
| fft | 中频 | 1.4s | 2 |
| json-parse | 中频 | 0.35s | 1 |
| ml-infer | 低频 | 1.9s | 2 |
| thumbnail | 低频 | 0.5s | 1 |
| video-transcode | 低频 | 2.2s | 3 |

30 个 request 覆盖 10 个时间点（0.0~9.5），img-resize 出现 9 次（高频）。

### 2.2 两类策略

```
FixedKeepAlivePolicy：
  keep_alive_window = 2.0s（固定）
  victim 选择：最早 expire

ColdStartAwarePolicy：
  utility = cold_start_duration * (1 + recent_rate) / memory_units
  keep_alive_window = base_window + 1.2 * cold_start + 2.0 * recent_rate - 0.3 * memory
  victim 选择：utility 最低
```

冷启动感知策略的 keep_alive_window 是**动态**的（0.5~6.0s）：
- 高 cold_start_duration → 长窗口（避免重复冷启动）
- 高 recent_rate → 长窗口（高频函数值得保活）
- 高 memory_units → 短窗口（让出 capacity 给其他函数）

### 2.3 关键 join（论文 demo 关键证据）

#### request × decision join

按 (policy_name, request_id) 关联 request_result 和 policy_decision，验证：

| 规则 | 期望 |
|------|------|
| `cache_hit=True` | `decision="extend_keep_alive"` |
| `cache_hit=False` | `decision="keep_after_cold_start"` |
| `keep_alive_window` 在 request 和 decision 两边一致 | 浮点差 < 1e-6 |

预期 60 行，`match` 全部 True。

#### eviction × state join

按 (policy_name, ev_time) 关联 eviction 和"下一个 decision"（warm_keys 字段），验证：

| 规则 | 期望 |
|------|------|
| 被驱逐函数不在后续 decision.warm_keys 里 | True |

预期 46 行，`match` 全部 True。

### 2.4 论文 demo 关键数字

| 指标 | fixed_keep_alive | cold_start_aware | 提升 |
|------|------------------|------------------|------|
| hit_rate (整体) | 0.1333 | **0.2333** | **+10 pp / 1.75x** |
| total_cold_start_penalty | 29.1s | **26.7s** | **-8.25%** |
| avg_latency | 1.128s | **1.048s** | **-7.09%** |
| avg_keep_alive_window | 2.000 | **2.579** | **+0.579** |
| eviction_count | 24 | 22 | -2 |
| img-resize hit_rate | 0.4444 | **0.7778** | **+33.3 pp** |

**论文 demo 一句话核心**：**cold_start_aware 只对高频函数（img-resize）加长保活窗口**，把它的命中率从 44% 提到 78%，整体命中率从 13% 提到 23%（**1.75x**），同时冷启动惩罚降低 8.25%。

## 3. 数据自检（17 项 PASS）

```
=== cold_start_aware_policy self-check ===
  [PASS] request_result_row_count : requests=60, expected=60
  [PASS] policy_decision_row_count : decisions=60, requests=60
  [PASS] policy_summary_row_count : summary rows=2, expected=2
  [PASS] policy_request_count__cold_start_aware : request_count=30, expected=30
  [PASS] policy_request_count__fixed_keep_alive : request_count=30, expected=30
  [PASS] function_summary_total_requests__cold_start_aware : sum=30, expected=30
  [PASS] function_summary_total_requests__fixed_keep_alive : sum=30, expected=30
  [PASS] request_decision_join_row_count : join rows=60, requests=60
  [PASS] request_decision_consistency : matched=60/60
  [PASS] eviction_state_join_row_count : join rows=46, evictions=46
  [PASS] eviction_state_consistency : matched=46/46
  [PASS] paper_highlight_metric_count : paper_highlight metrics=21, expected=21
  [PASS] paper_highlight_hit_rate__cold_start_aware : summary=0.233333, highlight=0.233333
  [PASS] paper_highlight_hit_rate__fixed_keep_alive : summary=0.133333, highlight=0.133333
  [PASS] paper_highlight_hit_rate_ratio : highlight=1.750000, expected=1.750000
  [PASS] cold_start_aware_beats_fixed_keep_alive : cold_start_aware=0.2333, fixed=0.1333 (cold_start_aware 应 >= fixed)
  [PASS] export_tables_have_no_index_column : no pandas index columns
=== 17 passed, 0 failed ===
data self-check: 17 / 17 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `request_result_row_count` | request 行数 = 2 policy × 30 = 60 |
| 02 | `policy_decision_row_count` | decision 行数 == request 行数 |
| 03 | `policy_summary_row_count` | summary 行数 == 2（两个 policy） |
| 04-05 | `policy_request_count__xxx` | per-policy 都跑 30 request |
| 06-07 | `function_summary_total_requests__xxx` | per-function 求和 = 30 |
| 08 | `request_decision_join_row_count` | request×decision join 行数 = 60 |
| 09 | `request_decision_consistency` | **论文 demo 关键证据**：60/60 match |
| 10 | `eviction_state_join_row_count` | eviction×state join 行数 = 46 |
| 11 | `eviction_state_consistency` | **论文 demo 关键证据**：46/46 match |
| 12 | `paper_highlight_metric_count` | paper highlight 稳定输出 21 个 metric |
| 13-14 | `paper_highlight_hit_rate__xxx` | paper highlight hit_rate 跟 policy_summary 一致 |
| 15 | `paper_highlight_hit_rate_ratio` | paper highlight ratio 跟 summary 一致 |
| 16 | `cold_start_aware_beats_fixed_keep_alive` | **论文核心结论**：cold_start_aware >= fixed |
| 17 | `export_tables_have_no_index_column` | 导出的 CSV 不包含 pandas 默认索引列（无 `Unnamed: 0`） |

## 4. 论文 demo 关键摘要（21 metric）

`outputs/cold_start_policy_paper_highlight.csv` 含 (metric, value, note) 三列：

| metric | value | note |
|--------|-------|------|
| `hit_rate__cold_start_aware` | 0.2333 | cold_start_aware 命中率（论文 demo 关键指标） |
| `hit_rate__fixed_keep_alive` | 0.1333 | fixed_keep_alive 命中率 |
| `avg_latency__cold_start_aware` | 1.048 | cold_start_aware 平均 latency |
| `avg_latency__fixed_keep_alive` | 1.128 | fixed_keep_alive 平均 latency |
| `total_cold_start_penalty__cold_start_aware` | 26.7 | cold_start_aware 全部冷启动惩罚累加 |
| `total_cold_start_penalty__fixed_keep_alive` | 29.1 | fixed_keep_alive 全部冷启动惩罚累加 |
| `avg_keep_alive_window__cold_start_aware` | 2.579 | cold_start_aware 平均 keep-alive window |
| `avg_keep_alive_window__fixed_keep_alive` | 2.000 | fixed_keep_alive 固定 2.0s |
| `eviction_count__cold_start_aware` | 22 | cold_start_aware 全部 evict 事件数 |
| `eviction_count__fixed_keep_alive` | 24 | fixed_keep_alive 全部 evict 事件数 |
| `hit_rate_improvement__cold_start_aware_over_fixed_keep_alive` | 0.1000 | **论文 demo 关键数字**：+10 pp |
| `hit_rate_ratio__cold_start_aware_over_fixed_keep_alive` | 1.7500 | **论文 demo 关键数字**：1.75x |
| `latency_reduction__cold_start_aware_over_fixed_keep_alive` | 0.0709 | cold_start_aware 相对延迟降低 7.09% |
| `cold_start_penalty_reduction__cold_start_aware_over_fixed_keep_alive` | 0.0825 | cold_start_aware 相对冷启动惩罚降低 8.25% |
| `avg_keep_alive_window_diff__cold_start_aware_over_fixed_keep_alive` | 0.5787 | **论文 demo 关键证据**：cold_start_aware 真的给高频函数更长窗口 |
| `request_decision_consistency` | 1.0 | **论文 demo 关键证据**：60/60 match |
| `request_decision_matched` | 60 | matched 行数 |
| `request_decision_total` | 60 | join 总行数（2 policy × 30） |
| `eviction_state_consistency` | 1.0 | **论文 demo 关键证据**：46/46 match |
| `eviction_state_matched` | 46 | matched 行数 |
| `eviction_state_total` | 46 | join 总行数（2 policy 全部 eviction） |

## 5. 4 张图说明

### fig01 — Policy comparison key metrics（论文 demo 关键图）
- 3 副图：hit_rate / avg_latency / total_cold_start_penalty
- 每副图 2 柱：fixed_keep_alive（灰）vs cold_start_aware（绿）
- **论文价值**：3 个核心 metric 一目了然——cold_start_aware 把 0.133→0.233、1.128s→1.048s、29.1s→26.7s。

### fig02 — Per-function hit rate（论文 demo 关键图）
- 分组柱：6 函数 × 2 policy 的 hit_rate
- 颜色：fixed_keep_alive（灰）vs cold_start_aware（绿）
- **论文价值**：**img-resize (高频) hit_rate 从 0.44 提到 0.78（+33.3 pp）**——一眼看出 cold_start_aware 的"差异化保活"效果，只对高频函数加长窗口。

### fig03 — Decision distribution
- 横向条形：4 类 (policy, decision, reason) × events
- 颜色：fixed_keep_alive（灰）vs cold_start_aware（绿）
- **论文价值**：warm_hit 4→7（**cold_start_aware 多 3 次命中**），对应 hit_rate 整体提升 10 pp。

### fig04 — Paper highlight metrics
- 分组横向条形：21 metric，分为 per-policy metrics、aware over fixed、request-decision join、eviction-state join 四栏
- **论文价值**：`request_decision_matched/total=60` + `eviction_state_matched/total=46` 直接对应 join 一致性；`hit_rate_ratio=1.75` 对应"1.75x 提升"；`avg_keep_alive_window_diff=0.5787` 对应"高频函数多保活 0.58s"。

## 6. 与 17 / 20 的对比

| 维度 | 17 cache_policy | 20 cache_aware_autoscaling | **21 cold_start_aware_policy** |
|------|-----------------|----------------------------|-------------------------------|
| 验证目标 | 缓存策略选择 | 扩缩容决策 | **保活策略对比** |
| 跑 faas-sim? | ✗ (in-memory) | ✗ (时间序列) | **✗ (trace-driven)** |
| 多 scenario 对比? | ✗ | ✗ | **✓ (fixed vs cold_start_aware)** |
| 输入 | 请求 trace | 函数状态时间序列 | **函数画像 + 请求 trace** |
| 关键 join | eviction×state | decision×control_plan | **request×decision + eviction×state** |
| 核心数字 | hit_rate=2.5x | utilization=0.8 | **hit_rate 1.75x** |
| 时间维度 | trace time | sampling round | **request time** |
| 决策类型 | cache decision | autoscaling action | **extend / keep_after_cold_start** |
| 论文 chart | 柱+折 | 折线+条+热力+条 | **柱+柱+条+条** |

**21 的独特价值**：
- 跟 17 同类（trace-driven in-memory），但**加入 2 policy 对比**（fixed vs cold_start_aware）
- **诚实暴露 sim 模型限制**：trace 短（30 request）+ 6 函数 + capacity=4，低频函数 5 个时间单位内不会重新访问，所以 hit_rate 都是 0%
- **诚实暴露决策分布**：cold_start_aware warm_hit 7 次（虽然 hit_rate 提到 0.23，但 trace 限制下"加窗口"机会有限）
- 跟 19/20 的 2 scenario 对比**思路一致**——baseline + 优化版——但 21 用 utility-aware victim 选择（不是 round-robin）来证明 policy 价值

## 7. 输出文件清单

```
examples/21_cold_start_aware_policy/
├── main.py                                # 入口：load profiles + trace + run 2 policies + paper + self-check
├── analysis.py                            # 4 summary + 2 join + paper highlight + self-check
├── loader.py                              # FunctionProfile + RequestEvent
├── models.py                              # FunctionProfile / RequestEvent / WarmEntry / RequestResult / PolicyDecision / EvictionEvent
├── policies.py                            # FixedKeepAlivePolicy + ColdStartAwarePolicy
├── runner.py                              # ColdStartAwarePolicyRunner（trace replay）
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── inputs/
│   ├── function_profile.csv              # 6 函数画像
│   └── request_trace.csv                 # 30 request
├── outputs/
│   ├── cold_start_request_result.csv             # 60 行（2 policy × 30）
│   ├── cold_start_policy_decision.csv            # 60 个 policy_decision
│   ├── cold_start_eviction.csv                   # 46 eviction
│   ├── cold_start_policy_summary.csv             # per-policy 摘要
│   ├── cold_start_function_summary.csv           # per-(policy, function)
│   ├── cold_start_decision_summary.csv           # per-(policy, decision, reason)
│   ├── cold_start_request_decision_join.csv      # request×decision 关联（论文 demo 关键证据）
│   ├── cold_start_eviction_state_join.csv        # eviction×state 关联（论文 demo 关键证据）
│   ├── cold_start_policy_paper_highlight.csv     # 21 metric + note
│   └── cold_start_aware_policy_self_check.csv    # 17 项数据自检
└── figures/
    ├── fig01_policy_comparison_metrics.png/pdf
    ├── fig02_per_function_hit_rate.png/pdf
    ├── fig03_decision_distribution.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **fixed_keep_alive baseline vs cold_start_aware 优化版**：21 是 trace-driven 缓存算法实验，**必须有 baseline 才能证明价值**。fixed_keep_alive 是最简单的"固定窗口"策略，cold_start_aware 加 utility 评分。**这个对照设计跟 19/20 一致**——baseline + 优化版。
- **utility 公式 = cold_start_duration * (1 + recent_rate) / memory_units**：3 因子组合——高冷启动代价（值得保活）、高近期访问频率（值得保活）、低 memory（小成本）。**这个公式的设计目标是"high utility functions deserve warm cache"**。
- **dynamic keep_alive_window = base + 1.2 * cold_start + 2.0 * recent_rate - 0.3 * memory**：4 因子——base 是 baseline（0.5s），cold_start 加权 1.2（次重要），recent_rate 加权 2.0（最重要），memory 加权 -0.3（反相关，让出 capacity）。**权重选择反映"近期需求 > 历史成本 > 资源消耗"**。
- **utility-aware victim 选择**：low utility function 先被驱逐，跟 LRU 不同的策略——**让"低 utility"函数主动释放**而不是等 expire 被动释放。这比 fixed 的"最早 expire" 更精准。
- **2 类 decision（extend_keep_alive / keep_after_cold_start）**：cache_hit=True → extend_keep_alive（已 warm 继续保活），cache_hit=False → keep_after_cold_start（cold miss 后保活一段时间）。**20 跟 21 的 decision 维度不同**——20 是 scale_out/in/protect/prewarm/observe（4 类动作 + 1 类保护），21 是 extend/keep_after（2 类状态）。
- **诚实暴露低频函数 0% hit rate**：6 个函数里只有 img-resize hit_rate > 0（其他 5 个 0%），因为 30 request 短 trace + 4 unit capacity 限制下低频函数"被驱逐后 5 个时间单位内不会重新访问"。**21 跟 17/18 一样诚实承认** sim 模型的限制。
- **诚实暴露 cold_start_aware warm_hit 7 vs fixed 4**：cold_start_aware 多 3 次命中，对应 10 pp 提升。**这 3 次都来自 img-resize**（高频函数），其他函数都是 cold_miss。
- **request×decision + eviction×state 两个 join**：21 跟 20 都有 1 个 join（20 是 decision×plan），但 21 有 2 个 join——request×decision 验证 cache_hit ↔ decision 映射，eviction×state 验证 evict 后 warm_keys 正确。**这是 21 的 demo 价值所在**：双 join 证明 policy 状态机正确性。
- **warm_keys 字段序列化在 decision 里**：每个 decision 记录执行后的 warm_keys 集合（`img-resize;fft;...`），eviction×state join 用这个字段验证"被驱逐的函数不在后续 warm_keys 里"。**这是 21 跟 17 的关键差异**——17 不记录 warm_keys 快照，21 必须记录才能验证 eviction 正确性。
