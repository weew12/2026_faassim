# 20_cache_aware_autoscaling — 缓存状态感知扩缩容（R_cache + R_load 组合决策）

> **目标**：同时计算缓存需求副本数 `R_cache` 和负载需求副本数 `R_load`，
> 组合得到最终目标副本数 `R_desired = max(R_cache, R_load)`，
> 并在 cache_capacity_budget 贪心选择下生成 5 类扩缩容动作
> （scale_out / scale_in / protect / prewarm / observe）和 control_plan，
> 验证每个 decision 都对应一个 plan 且 action / target_replicas / safe_to_execute 语义一致。

## 1. 复现步骤

```bash
# 1) 跑主程序（5 time × 4 function = 20 state，13/13 PASS）
python -u examples/20_cache_aware_autoscaling/main.py

# 2) 跑绘图（4 张图：R_cache vs R_load 时间序列 + action 分布 + per-function delta 热力 + paper highlight）
python -u examples/20_cache_aware_autoscaling/plot.py
```

输出：
- `outputs/cache_aware_autoscaling_decision.csv`：20 state 的完整决策明细
- `outputs/cache_aware_autoscaling_control_plan.csv`：20 control_plan
- `outputs/cache_aware_autoscaling_decision_plan_join.csv`：decision × plan 关联（论文 demo 关键证据）
- `outputs/cache_aware_autoscaling_action_summary.csv`：per-(action, reason) 摘要
- `outputs/cache_aware_autoscaling_function_summary.csv`：per-function 摘要
- `outputs/cache_aware_autoscaling_time_summary.csv`：per-time 总副本需求摘要
- `outputs/cache_aware_autoscaling_paper_highlight.csv`：33 metric + note
- `outputs/cache_aware_autoscaling_self_check.csv`：13 项数据自检
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 三层副本数计算

```
R_cache_raw = 1 if in_flight > 0
           = 0 if (n_req == 0 AND last_seen_age >= idle_age_threshold=6s)
           = 1 if cache_utility >= cache_utility_threshold=1.0
           = 0 otherwise

R_load_raw = ceil(request_rate / (replica_capacity_rps * target_utilization=0.70))

R_desired = clamp[min=0, max=5](max(R_cache, R_load))
```

R_cache 关注**冷启动收益保护**，R_load 关注**当前负载需求**。组合 max 避免两类错误：
- 只看负载：低负载但高冷启动函数会被过早缩到 0
- 只看缓存：高负载函数可能无法及时扩容

### 2.2 cache 评分公式

```
cold_benefit = avg_cold_start * (0.6 * n_req + 1.5 * cold_miss_count + 2.0 * request_rate)
resource_cost = max(memory_units, 1) * resource_weight (= 0.60)
cache_utility = cold_benefit / max(resource_cost, epsilon)
```

### 2.3 5 类扩缩容动作

| action | 触发条件 | 含义 |
|--------|---------|------|
| `scale_out` | r_desired > current_replicas AND r_load >= r_cache | 负载触发的扩容 |
| `prewarm` | r_desired > current_replicas AND r_cache > r_load | 缓存触发的预热 |
| `protect` | r_desired < current_replicas AND in_flight > 0 | 在飞请求保护（不缩） |
| `scale_in` | r_desired < current_replicas AND no in_flight | 缩容到目标数 |
| `observe` | r_desired == current_replicas | 无动作 |

### 2.4 容量预算（cache_capacity_budget_units = 5）

- 5 time × 4 function = 20 decision，每个 time 独立应用 budget
- 贪心选 r_cache 候选（按 cache_utility 降序），直到 budget 用满
- 选中：`capacity_status = cache_selected_within_budget`
- 未选中：`capacity_status = cache_budget_limited`，r_cache 被削为 0
- R_load 触发的需求**不被 budget 削减**（即使 budget 用满也要扩）

### 2.5 关键 join（论文 demo 关键证据）

`outputs/cache_aware_autoscaling_decision_plan_join.csv` 按 (time, function_name) 关联 decision 和 control_plan，验证：

| 字段 | 验证规则 |
|------|---------|
| `action == plan_action` | decision.action 必须等于 plan.control_action |
| `target_replicas == r_desired` | plan.target_replicas 必须等于 decision.r_desired |
| `scale_in AND in_flight > 0 → safe_to_execute=False` | 缩容时不能杀在飞请求 |
| `r_desired == current_replicas → executor_required=False` | 无需执行器介入 |

预期 20 行，`match` 全部 True。

## 3. 数据自检（13 项 PASS）

```
=== cache_aware_autoscaling self-check ===
  [PASS] decision_plan_count_match : decisions=20, plans=20
  [PASS] decision_count : decisions=20
  [PASS] r_desired_equals_max_r_cache_r_load : all 20 decisions satisfy r_desired=max(r_cache, r_load)
  [PASS] cache_budget_within_limit : per-time violations=0, max selected memory per time=4, budget=5
  [PASS] decision_plan_join_row_count : join rows=20, decisions=20
  [PASS] decision_plan_join_match : matched=20/20
  [PASS] action_values_valid : observed=['observe', 'protect', 'scale_in', 'scale_out']
  [PASS] r_desired_in_clamp_range : r_desired range=[0, 4], expected subset of [0, 5]
  [PASS] paper_highlight_action_count_sum : sum of action_count metrics=20, decisions=20
  [PASS] paper_highlight_decision_plan_consistency : decision_plan_consistency=1.0000
  [PASS] paper_highlight_cache_budget_utilization : highlight=0.800000, expected=0.800000
  [PASS] scale_in_in_flight_not_safe : unsafe scale_in rows with in_flight>0: 0
  [PASS] export_tables_have_no_index_column : no pandas index columns
=== 13 passed, 0 failed ===
data self-check: 13 / 13 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `decision_plan_count_match` | decision 行数 == plan 行数（20=20） |
| 02 | `decision_count` | decision 行数 > 0 |
| 03 | `r_desired_equals_max_r_cache_r_load` | **核心**：所有 20 个 decision 都满足 r_desired = max(r_cache, r_load) |
| 04 | `cache_budget_within_limit` | per-time 选中 memory ≤ 5（max=4 ≤ 5） |
| 05 | `decision_plan_join_row_count` | decision×plan join 行数 == decision 行数（20） |
| 06 | `decision_plan_join_match` | decision×plan join 100% match（20/20） |
| 07 | `action_values_valid` | action 字段只取 5 类有效值 |
| 08 | `r_desired_in_clamp_range` | r_desired 在 [min=0, max=5] 范围内 |
| 09 | `paper_highlight_action_count_sum` | paper highlight 5 类 action_count 加总 = 20 |
| 10 | `paper_highlight_decision_plan_consistency` | paper highlight decision_plan_consistency = 1.0 |
| 11 | `paper_highlight_cache_budget_utilization` | budget 利用率与 per-time max 一致 |
| 12 | `scale_in_in_flight_not_safe` | scale_in 不杀在飞请求 |
| 13 | `export_tables_have_no_index_column` | 导出的 CSV 不包含 pandas 默认索引列（无 `Unnamed: 0`） |

## 4. 论文 demo 关键摘要（33 metric）

`outputs/cache_aware_autoscaling_paper_highlight.csv` 含 (metric, value, note) 三列：

| metric | value | note |
|--------|-------|------|
| `action_count__scale_out` | 5 | scale_out 动作的 state 数（论文 demo 关键分布） |
| `action_count__scale_in` | 6 | scale_in 动作的 state 数 |
| `action_count__protect` | 8 | protect 动作的 state 数（最常见，r_desired 经常等于 current） |
| `action_count__prewarm` | 0 | prewarm 动作的 state 数（**诚实说明**：数据中 R_cache > R_load 一次都没发生） |
| `action_count__observe` | 1 | observe 动作的 state 数 |
| `r_load_dominant_events` | 5 | R_load > R_cache 主导 events（5/20 = 25%） |
| `r_cache_only_events` | 0 | R_cache > 0 且 R_load == 0 events（**诚实说明**：cache-only 保护 0 次） |
| `r_both_active_events` | 15 | R_cache > 0 且 R_load > 0 events（cache+load 同时保护） |
| `r_neither_active_events` | 4 | R_cache == 0 且 R_load == 0 events（idle 状态） |
| `r_load_dominant_ratio` | 0.25 | R_load 主导占比（论文 demo 关键数字） |
| `cache_budget_used` | 19 | **诚实说明**：是 5 time 累加的 selected memory 之和；单一 time max=4 ≤ 5 |
| `cache_budget_max_used_per_time` | 4 | 单个 time 内选中 cache memory 的最大值 |
| `cache_budget_total` | 5 | 总 cache budget |
| `cache_budget_utilization` | 0.8 | **论文 demo 关键数字**：单一 time 利用率 4/5 = 80% |
| `r_cache_rejected_by_budget` | 1 | R_cache > 0 但被 budget 拒绝的 events（video-transcode 长期 idle 仍占 3 unit） |
| `decision_plan_consistency` | 1.0 | **论文 demo 关键证据**：decision × plan join 100% match |
| `decision_plan_matched` | 20 | matched 行数 |
| `decision_plan_total` | 20 | join 总行数 |
| `per_time_total_r_cache__{0..4}` | 3/4/3/3/2 | 5 个时间点 R_cache 总和 |
| `per_time_total_r_load__{0..4}` | 3/6/8/3/3 | 5 个时间点 R_load 总和 |
| `per_time_total_r_desired__{0..4}` | 3/6/8/3/3 | 5 个时间点 R_desired 总和（**R_load 主导**） |

**关键发现**：
- **R_load 在 time=1/2 主导扩容**：total_r_desired 从 3 跳到 6→8，**全部由 R_load 触发**（total_r_cache 只 4→3 下降）
- **cache_budget 80% 利用**：单一 time max=4 ≤ 5 budget
- **video-transcode 长期 idle 仍想占 3 unit**（memory=3），被 budget 拒绝
- **decision × plan join 100% 一致**：20/20 全部 match

## 5. 4 张图说明

### fig01 — R_cache vs R_load time series（论文 demo 关键图）
- x = time (0-4), y = total replicas across 4 functions
- 3 折线：total_r_cache（蓝圆点）/ total_r_load（橙方块）/ total_r_desired（灰虚线三角）
- 每个 time 点标 R_desired 数字
- **论文价值**：**一眼看出 R_load 在 time=1/2 主导扩容**（3→6→8），R_desired = R_load（因为 max 永远取 R_load）；time=3/4 回归 baseline。

### fig02 — Action distribution（论文 demo 关键图）
- 横向条形：5 类 (action, reason) × events
- 颜色：scale_out=绿、protect=蓝、observe=灰、scale_in=红、prewarm=橙
- **论文价值**：protect 8 是最常见（r_desired 经常等于 current_replicas），scale_out 5（time=1/2 fft/img-resize 扩容），scale_in 6（video-transcode 长期 idle + time=3 fft/img-resize）。

### fig03 — Per-function delta heatmap（论文 demo 关键图）
- 4 行（fft / img-resize / json-parse / video-transcode）× 5 列（time）
- 颜色：RdYlGn 发散色板（+2 深绿 / 0 黄 / -2 深红）
- 标注：每个 cell 标 +N/-N/0
- **论文价值**：**视频转码长期缩容**（time=0/2/3/4 全 -1）、**json-parse 全程 0 delta**（最稳）、**fft 峰值 +2 at time=2**。

### fig04 — Paper highlight metrics
- 分组横向条形：33 metric，分为 action counts、R-cache/R-load mix、budget/plan checks、per-time totals 四栏
- **论文价值**：
  - `decision_plan_total=20` + `decision_plan_matched=20` 直接对应"20/20 一致"
  - `r_both_active_events=15` 对应"cache+load 同时保护 75%"
  - `cache_budget_utilization=0.8` 对应"80% 利用"
  - `r_cache_only_events=0` + `action_count__prewarm=0` **诚实暴露**"cache-only 保护 0 次"

## 6. 与 02-19 的 demo 价值对比

| 维度 | 02 LB | 11 fault | 17 cache | 18 decision | **19 cache-aware scheduler** | **20 cache-aware autoscaling** |
|------|-------|---------|----------|-------------|------------------------------|-------------------------------|
| 验证目标 | 路由均衡 | 故障模型 | 缓存策略 | 缓存决策 | **缓存状态感知调度** | **缓存状态感知扩缩容** |
| 跑 faas-sim? | ✓ | ✓ | ✗ (in-memory) | ✗ (静态画像) | ✓ | **✗ (时间序列)** |
| 多 scenario 对比? | ✗ | ✗ | ✗ | ✗ | ✓ (blind vs aware) | **✗ (单 scenario)** |
| 输入 | 无 | 故障事件 | 请求 trace | 函数画像快照 | cache snapshot + workload | **函数状态时间序列** |
| 关键 join | route×probe | event×state | eviction×state | decision×hint | **probe×inv** | **decision×control_plan** |
| 核心数字 | balance_std=0 | fault=2.49x | hit=2.5x | consistency=1.0 | **hit_rate 0%→100%** | **utilization=0.8** |
| 时间维度 | ✗ | ✗ | ✗ | ✗ | ✗ | **✓ (5 time × 4 fn)** |
| 论文 chart | 阶梯图 | 柱+柱+散 | 柱+折 | 柱+条+柱+条 | 柱+柱+热力+条 | **折线+条+热力+条** |

**20 的独特价值**：
- 第一个**时间序列驱动**样例（5 time × 4 function 状态快照）
- 第一个 **R_cache + R_load 组合** 公式（max 避免两类错误）
- 第一个**按 5 类 action 分类**决策（scale_out / scale_in / protect / prewarm / observe）
- 第一个**有 protect 动作**（在飞请求保护，避免直接缩容）
- **诚实暴露**：R_cache_only_events=0 + prewarm=0（说明这组数据 R_cache 单独保护需求 0，cache 价值只在 R_both 中体现）
- 论文 demo 关键：**R_load 在 time=1/2 主导扩容**（3→6→8），cache_budget 80% 利用

## 7. 输出文件清单

```
examples/20_cache_aware_autoscaling/
├── main.py                                # 入口：load states + autoscaler + paper highlight + self-check
├── analysis.py                            # 4 summary + decision×plan join + paper highlight + self-check
├── autoscaler.py                          # CacheAwareAutoscaler（R_cache + R_load + budget + plan）
├── loader.py                              # FunctionState + load_function_states
├── models.py                              # FunctionState / AutoscalingConfig / Decision / ControlPlan
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── inputs/
│   └── function_state_timeseries.csv     # 5 time × 4 function = 20 state
├── outputs/
│   ├── cache_aware_autoscaling_decision.csv            # 20 decision 明细
│   ├── cache_aware_autoscaling_control_plan.csv        # 20 control_plan
│   ├── cache_aware_autoscaling_action_summary.csv     # per-(action, reason) 摘要
│   ├── cache_aware_autoscaling_function_summary.csv   # per-function 摘要
│   ├── cache_aware_autoscaling_time_summary.csv       # per-time 总副本需求
│   ├── cache_aware_autoscaling_decision_plan_join.csv # 论文 demo 关键证据
│   ├── cache_aware_autoscaling_paper_highlight.csv    # 33 metric + note
│   └── cache_aware_autoscaling_self_check.csv         # 13 项数据自检
└── figures/
    ├── fig01_r_cache_vs_load_timeseries.png/pdf
    ├── fig02_action_distribution.png/pdf
    ├── fig03_per_function_delta_heatmap.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **max(R_cache, R_load) 而非加权求和**：用 max 而非加权求和，可以保证**两类需求任一满足都触发副本保护**。加权求和会让低需求被高需求掩盖，max 永远不会掩盖。
- **cache_budget 只约束 R_cache，不约束 R_load**：R_load 来自当前真实请求负载，是必须满足的（用户请求会失败）。R_cache 来自冷启动收益预测，可以被预算约束。**这是 20 跟 18 的关键区别**——18 同样有 capacity_budget，但 18 是静态画像驱动（无 R_load），20 是时间序列驱动（有 R_load）。
- **5 类 action 而非 3 类**：18 的 4 类决策（keep_warm / prewarm / eviction / observe）是"缓存策略分类"，20 的 5 类动作（scale_out / scale_in / protect / prewarm / observe）是"具体扩缩容动作"。**protect** 是 20 独有——当 r_desired < current_replicas 但有 in_flight 请求时，不缩容以保护在飞请求。这是边缘 Serverless 的关键场景（cold start 感知 + 在飞保护）。
- **per-time 独立 budget 而非全局累加**：5 个 time 各自独立应用 budget=5，不是跨 time 累加。这样设计模拟"实时调度器"——每个 time 看到的 capacity 限制相同，不需要"过去 time 用了多少"。
- **3 权重评分公式（与 18 略不同）**：20 用 `0.6 * n_req + 1.5 * cold_miss_count + 2.0 * request_rate`，18 用 `0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate`。**`cold_miss_count` 权重 1.5 > 18 的 1.4**——因为 20 多了 in_flight_requests 字段可以更精确判断 cold miss 真实损失。
- **诚实暴露 prewarm=0 / r_cache_only_events=0**：这组数据 5 time × 4 function 中**没有一次** R_cache > R_load 单独保护。原因是 in_flight_requests > 0 时 R_cache=1，但同一时间 R_load 经常也 > 0（因为 request_rate 都在 base 之上）。**论文 demo 关键**：cache 价值的"独立贡献"难分离，cache 主要在 R_both 中体现。
- **cache_budget_used=19 vs cache_budget_utilization=0.8 的差异**：19 是 5 time 累加（select=True 的 memory 在 20 row 求和），0.8 是单一 time max 利用率。**README 诚实说明**这是两个不同维度的指标。
- **clamp [min=0, max=5]**：允许 scale_in 到 0（idle 释放）+ 允许 scale_out 到 5（避免爆 budget）。**与 18 的 capacity_budget=4 unit 不同**——20 的 max_replicas=5 是**单函数上限**，不是集群总容量。
- **scale_in 时 safe_to_execute=False（in_flight > 0）**：扩缩容 plan 必须保证在飞请求不被杀。这是 20 跟 17/18 的**核心安全语义**——17/18 不涉及 in_flight（17 是 hit/miss 策略，18 是静态决策），20 是实时扩缩容，必须保护在飞。
