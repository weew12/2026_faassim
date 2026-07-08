# 18_cache_decision — 冷启动感知缓存决策（静态画像驱动）

> **目标**：基于函数画像快照计算冷启动收益、资源代价和缓存效用，
> 生成 keep_warm / prewarm_candidate / eviction_candidate / observe 四类决策，
> 并在 capacity_budget 贪心选择下生成控制建议（control_hint），
> 验证每个决策都能正确映射到 control_action。

## 1. 复现步骤

```bash
# 1) 跑决策实验（静态画像驱动，7 函数 × 4 unit budget = 13/13 PASS）
python -u examples/18_cache_decision/main.py

# 2) 跑绘图（4 张图：决策分布 + utility 排序 + capacity 利用 + 论文摘要）
python -u examples/18_cache_decision/plot.py
```

输出：
- `outputs/`：7 个 csv（detail / summary / rank / eviction / control_hint / decision_hint_join / paper_highlight）+ **cache_decision_self_check**
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 决策类型

| 决策 | 含义 | control_action | 触发条件 |
|------|------|----------------|---------|
| `keep_warm` | 继续保护当前 warm 副本 | `protect_current_replica` | 有 in_flight 请求 / utility >= 1.20 |
| `prewarm_candidate` | 可作为预热候选 | `scale_to_one_if_selected` | 无副本 + utility >= 1.00 |
| `eviction_candidate` | 可作为释放候选 | `scale_to_zero_candidate` | 长期空闲（last_seen_age >= 6s + n_req=0）/ utility <= 0.35 |
| `observe` | 暂不动作 | `observe` | 其他情况 |

### 2.2 评分公式

```
cold_benefit = avg_cold_start * (0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate)
resource_cost = memory_units * resource_weight (= 0.60)
utility_score = cold_benefit / resource_cost
```

权重说明：
- `0.6 * n_req`：历史请求量（基础权重）
- `1.4 * cold_miss_count`：实际冷启动缺失（强化权重，因为这是已经发生的浪费）
- `2.0 * request_rate`：当前请求速率（最高权重，因为反映未来需求）

### 2.3 容量预算（capacity_budget = 4 unit）

- 7 个函数按 priority 降序排列
- 贪心选 keep_warm / prewarm_candidate 直到 budget 用满
- `selected_by_budget=True` 的函数会被实际保护/预热，其他会被 budget 限制

### 2.4 关键 join（论文 demo 关键证据）

`cache_decision_hint_join.csv` 按 `function_name` 关联 decision 和 control_hint，验证：

| decision | 期望 hint_action | safe_to_execute 条件 |
|----------|-------------------|---------------------|
| `keep_warm` | `protect_current_replica` | 始终 True |
| `prewarm_candidate` | `scale_to_one_if_selected` | `selected_by_budget=True` 时 True |
| `eviction_candidate` | `scale_to_zero_candidate` | `in_flight_requests=0` 时 True |
| `observe` | `observe` | 始终 True |

## 3. 数据自检（13 项 PASS）

```
data self-check: 13 / 13 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `decision_count` | decision 行数 == profile 数（7） |
| 02 | `hint_count` | hint 行数 == decision 行数 |
| 03 | `decision_hint_join_row_count` | decision × hint join 行数 == decision 行数（7） |
| 04 | `decision_hint_join_match` | decision × hint 关联 100% match（7/7） |
| 05 | `decision_values_valid` | 决策字段只取 4 类有效值 |
| 06 | `capacity_budget_within_limit` | 选中 memory ≤ capacity_budget（4 ≤ 4） |
| 07 | `keep_warm_all_selected_by_budget` | 所有 keep_warm 都被 budget 选中 |
| 08 | `eviction_candidate_no_in_flight` | eviction_candidate 都不带 in_flight > 0 |
| 09 | `keep_warm_budget_greedy` | keep_warm 贪心用满 budget（4/4） |
| 10 | `hint_action_mapping_valid` | 4 类 decision 都映射到期望 control_action |
| 11 | `paper_highlight_decision_count_sum` | paper highlight 4 类 decision_count 加总 = 7 |
| 12 | `paper_highlight_decision_hint_consistency` | paper highlight `decision_hint_consistency` = 1.0 |
| 13 | `export_tables_have_no_index_column` | 导出的 CSV 不包含 pandas 默认索引列（无 `Unnamed: 0`） |

## 4. 论文 demo 关键摘要（18 条）

`outputs/cache_decision_paper_highlight.csv` 包含（沿用 02-17 的 metric/value/note 三列模式）：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `total_functions` | 7 | 输入函数画像数 |
| `total_decision_types_observed` | 4 | 出现的决策类型数 |
| `total_selected_by_budget` | 3 | 被 budget 选中的函数数 |
| `decision_count__keep_warm` | 3 | keep_warm 决策函数数 |
| `decision_count__prewarm_candidate` | 2 | prewarm_candidate 决策函数数 |
| `decision_count__eviction_candidate` | 1 | eviction_candidate 决策函数数 |
| `decision_count__observe` | 1 | observe 决策函数数 |
| `top_utility_rank_1__img-resize` | 57.87 | utility 排名第 1（论文 demo 关键数字） |
| `top_utility_rank_2__fft` | 25.43 | utility 排名第 2 |
| `top_utility_rank_3__ml-infer` | 20.58 | utility 排名第 3 |
| `lowest_utility__thumbnail` | 0.0 | utility 最低（应 = eviction_candidate） |
| `capacity_budget_used` | 4 | 被选中 keep_warm 实际占用 memory |
| `capacity_budget_total` | 4 | 总 budget |
| `capacity_budget_utilization` | 1.0 | **论文 demo 关键数字**：capacity 100% 利用 |
| `decision_hint_consistency` | 1.0 | **论文 demo 关键数字**：decision × hint 100% 一致 |
| `decision_hint_matched` | 7 | matched 行数 |
| `decision_hint_total` | 7 | join 总行数 |
| `eviction_reason__thumbnail` | idle_warm_instance | thumbnail 被判定为 eviction 的理由 |

## 5. 4 张图说明

### fig01 — Cache decision distribution（论文 demo 关键图）
- 柱状图：4 类决策 × 函数计数
- 颜色按 decision 类型（绿=keep_warm, 橙=prewarm_candidate, 红=eviction_candidate, 灰=observe）
- **论文价值**：一眼看出决策分布（3 keep_warm + 2 prewarm + 1 eviction + 1 observe），证明决策器在 capacity_budget=4 下能合理分配资源。

### fig02 — Utility score ranking
- 横向条形图：7 个函数按 utility_score 升序
- 颜色按 decision 类型
- 标签格式：`{score} ({decision})`
- **论文价值**：展示 utility 排序——img-resize 57.87 > fft 25.43 > ml-infer 20.58 > json-parse 10.62 > report-gen 2.38 > video-transcode 0.98 > thumbnail 0.00。**img-resize 是最高 cache 价值**。

### fig03 — Capacity budget utilization（论文 demo 关键图）
- 柱状图：3 个选中 keep_warm 函数的 memory 占用
- capacity_budget=4 参考线
- 标题显示 used/total = 4/4
- **论文价值**：视觉证明 capacity_budget 100% 利用，3 个 keep_warm 函数（report-gen=2 + img-resize=1 + json-parse=1）正好用满 4 unit 预算。

### fig04 — Paper Highlight Metrics
- 分组横向条形图：18 个 metric，分为决策计数、utility 排名、budget/一致性三栏
- **论文价值**：最显眼的 bar 是 `top_utility_rank_1__img-resize=57.87`（论文 demo 关键数字），其他聚合 metric（`total_functions=7` / `total_selected_by_budget=3` / `decision_hint_total=7`）也是论文里可以直接引用的数字。

## 6. 与 02-17 的 demo 价值对比

| 维度 | 02 LB | 16 cosim | 17 cache | **18 decision** |
|------|-------|---------|----------|-----------------|
| 验证目标 | 路由均衡 | 外部控制器影响 | 缓存策略效果 | **缓存决策过程** |
| 跑 faas-sim? | ✓ | ✓ | ✗ (in-memory) | **✗ (静态画像)** |
| 输入 | 无 | 外部 trace | 请求 trace | **函数画像快照** |
| 探针 | dispatch | dispatch+cosim | request+state+eviction | **detail+hint+join** |
| 关键 join | route×probe | probe×inv | eviction×state | **decision×hint** |
| 核心数字 | balance_std=0 | impact=2.49x | hit_rate_ratio=2.5x | **decision_hint_consistency=1.0** |
| 论文 chart | 阶梯图 | 柱+柱+阴影散点 | 柱+分组柱+折线 | **柱+条+柱+条** |

**18 的独特价值**：18 是 02-17 中**唯一一个"静态画像驱动决策"**的样例。
- 02-11：跑 faas-sim，验证仿真机制
- 12-13：跑 faas-sim + 外部 trace/cold start
- 14：跑 faas-sim × 多 case 批量
- 15：读 14 的 csv 做聚合
- 16：跑 faas-sim + 外部控制循环
- 17：不跑 faas-sim，trace 驱动的缓存算法
- **18：不跑 faas-sim，静态画像驱动的缓存决策**

18 跟 17 的区别是 17 跑 trace 模拟每次请求的 cache hit/miss，18 直接读"过去"的画像快照做一次性的容量分配决策。

## 7. 输出文件清单

```
examples/18_cache_decision/
├── main.py                                # 入口：load profiles + evaluate + export
├── profiles.py                            # FunctionProfile + load_profiles
├── decision_model.py                      # CacheDecisionConfig / CacheDecision / ControlHint
├── advisor.py                             # CacheDecisionAdvisor（评分+分类+capacity 选择）
├── analysis.py                            # 4 summary + decision×hint join + paper_highlight + self_check
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── inputs/
│   └── function_profile_snapshot.csv     # 7 个函数画像
├── outputs/
│   ├── cache_decision_detail.csv          # 每个函数的完整决策明细
│   ├── cache_decision_summary.csv         # per-(decision, capacity_status) 摘要
│   ├── cache_decision_rank.csv            # keep_warm / prewarm 按 priority 排序
│   ├── cache_eviction_candidate.csv      # eviction_candidate 函数列表
│   ├── cache_control_hint.csv             # 每函数 control_action
│   ├── cache_decision_hint_join.csv       # decision × hint 关联（论文 demo 关键证据）
│   ├── cache_decision_paper_highlight.csv # 论文 demo 关键摘要（18 metric + note）
│   └── cache_decision_self_check.csv      # 13 项数据自检
└── figures/
    ├── fig01_decision_distribution.png/pdf
    ├── fig02_utility_score_ranking.png/pdf
    ├── fig03_capacity_budget_utilization.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **静态画像而非 trace 驱动**：18 不跑 faas-sim、不读请求 trace，而是直接读"过去"的函数画像快照（n_req / cold_miss_count / request_rate / last_seen_age / in_flight_requests）。这让 18 能专注于"决策过程"——把画像数据变成 4 类决策 + control_hint，不被仿真框架的复杂度掩盖。
- **3 权重评分公式**：用 `(0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate)` 作为冷启动收益的复合权重。`0.6` 给历史请求、`1.4` 给实际冷启动缺失、`2.0` 给当前请求速率（最高权重，因为反映未来需求）。这个公式不依赖未来访问预测，是无需预测的最简可用版本。
- **贪心 capacity budget 选择**：用 priority 降序贪心选 keep_warm/prewarm_candidate，直到 budget 用满。`selected_by_budget=True` 标记是否实际被选中。**所有 keep_warm 都被 budget 选中**（因为 keep_warm priority >= 1000 有 in_flight_request_protection 保护）。
- **decision × hint 4 类映射规则**：每个 decision 必须正确映射到对应 control_action 和 safe_to_execute。`eviction_candidate` 还需要 `in_flight_requests=0` 才能 safe_to_execute=True（保护正在执行的请求）。这 4 类映射规则在 `build_decision_hint_join` 里硬编码验证，确保 100% 一致。
- **诚实承认 priority 跳跃**：report-gen 的 utility_score 只有 2.38，但因为它有 `in_flight_requests=1 + current_replicas=1`（有 in-flight 保护），priority 加了 1000 变成 1002.38，反超 img-resize (priority=57.87)。这展示了 priority 的"安全优先"语义——`in_flight_request_protection` 永远比 `high_cold_start_utility` 优先。
- **3 决策维度 + 1 control_action 维度**：decision 是"逻辑分类"（keep_warm / prewarm / eviction / observe），hint 是"物理动作"（protect / scale_to_one / scale_to_zero / observe）。self_check 验证两者的语义一致，避免"逻辑上是 keep_warm 但动作是 scale_to_zero"这种 internal inconsistency。
