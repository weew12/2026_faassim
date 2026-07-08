# 23_thesis_experiment — 论文实验组织（LoadOnly vs FaasCache vs CacheAwareJoint）

> **目标**：整合 17/18/19/20/22 的核心机制（policy 评分 + R_cache/R_load + 节点选择 + 扩缩容决策）到**一个 trace-driven 框架**，
> 跑 3 case（LoadOnly / FaasCache / CacheAwareJoint）对比，
> 验证 CacheAwareJoint 在 3 缓存维度 + latency 全面胜出，并证明 `R_desired = max(R_cache, R_load)` 公式生效。

## 1. 复现步骤

```bash
# 1) 跑主程序（5 函数 × 6 节点 × 35 request × 3 case = 105 result，23/23 PASS）
python -u examples/23_thesis_experiment/main.py

# 2) 跑绘图（4 张图：3 缓存维度 + latency + R_cache vs R_load + paper highlight）
python -u examples/23_thesis_experiment/plot.py
```

输出：
- `outputs/thesis_request_result.csv`：105 行（3 case × 35 request）
- `outputs/thesis_control_decision.csv`：105 个 control_decision（R_cache / R_load / R_desired）
- `outputs/thesis_candidate_score.csv`：630 行（6 candidate × 105）
- `outputs/thesis_eviction_event.csv`：驱逐事件
- `outputs/thesis_policy_summary.csv`：per-(case, policy) 摘要
- `outputs/thesis_function_summary.csv`：per-(case, policy, function) 摘要
- `outputs/thesis_phase_summary.csv`：per-(case, policy, phase) 摘要
- `outputs/thesis_control_summary.csv`：per-(case, policy, action, reason) 摘要
- `outputs/thesis_baseline_comparison.csv`：以 LoadOnly 为 baseline 的相对改进
- `outputs/thesis_result_candidate_join.csv`：result × candidate 关联（论文 demo 关键证据）
- `outputs/thesis_request_decision_join.csv`：request × decision 关联（论文 demo 关键证据）
- `outputs/thesis_paper_highlight.csv`：49 metric + note
- `outputs/thesis_experiment_self_check.csv`：23 项数据自检
- `outputs/thesis_experiment_report.md`：Markdown 实验报告
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 3 case 对比

| case | R_cache 评分 | R_load 评分 | 节点选择 | 作用 |
|------|-------------|-------------|----------|------|
| `LoadOnly` | ✗ | ✓ | 资源 only | **负载基线**（无 cache 优化） |
| `FaasCache` | ✓ | ✗ | 资源 only | cache-only 基线（**调度不感知缓存**） |
| `CacheAwareJoint` | ✓ | ✓ | cache + resource + locality + load + latency | **完整策略**（论文 demo 关键 case） |

### 2.2 3 缓存维度

| 维度 | 含义 | 命中收益 |
|------|------|---------|
| `warm` | 函数 warm 实例缓存 | 0 cold_start 惩罚 |
| `image` | 镜像缓存 | 0 image_pull 惩罚 |
| `data` | 数据缓存 | 0 data_fetch 惩罚 |

### 2.3 R_desired 公式

```
R_desired = max(R_cache, R_load)
```

**3 case 的 R_cache vs R_load 行为**：
- `LoadOnly`: R_cache=0（关闭 cache 评分），R_load=1（按负载），R_desired=1
- `FaasCache`: R_cache=0.97（按 cache utility），R_load=0（关闭 load 评分），R_desired=0.97
- `CacheAwareJoint`: **R_cache=0.97 + R_load=1**（同时），R_desired=1

**论文核心结论**：**CacheAwareJoint 是唯一同时 R_cache + R_load 都 > 0 的策略**——`max` 公式生效。

### 2.4 2 个关键 join

#### result × candidate join

按 (case, policy, request) 关联 result 和 candidate，验证：

| 规则 | 含义 |
|------|------|
| cache_aware_joint 选中的节点是 max-score | 调度评分正确 |
| faascache / load_only 不要求 max-score | 它们的调度逻辑不基于 candidate 评分 |
| 3 case 都要求 cache_hit / image_cache_hit / data_cache_hit / latency 一致 | 评估指标正确 |

预期 105 行，`match` 全部 True（cache_aware_joint 35/35 must be max-score）。

#### request × decision join

按 (case, policy, request) 关联 result 和 control_decision，验证：

| 规则 | 含义 |
|------|------|
| `result.r_cache == decision.r_cache` | R_cache 一致 |
| `result.r_load == decision.r_load` | R_load 一致 |
| `result.r_desired == decision.r_desired` | R_desired 一致 |

预期 105 行，`match` 全部 True。

## 3. 数据自检（23 项 PASS）

```
=== thesis_experiment self-check ===
  [PASS] request_result_row_count : requests=105, expected=105
  [PASS] candidate_score_count : candidates=630, requests=105
  [PASS] candidate_count_per_request_consistent : candidate groups=105, candidates per request=6
  [PASS] policy_summary_row_count : summary rows=3, expected=3
  [PASS] case_request_count__cache_aware_joint : request_count=35
  [PASS] case_request_count__faascache : request_count=35
  [PASS] case_request_count__load_only : request_count=35
  [PASS] baseline_comparison_row_count : 3
  [PASS] baseline_comparison_has_load_only
  [PASS] result_candidate_join_row_count : join rows=105, requests=105
  [PASS] result_candidate_join_match : 105/105
  [PASS] cache_aware_joint_candidate_max_score : 35/35
  [PASS] request_decision_join_row_count : join rows=105, requests=105
  [PASS] request_decision_join_match : 105/105
  [PASS] paper_highlight_metric_count : paper_highlight metrics=49, expected=49
  [PASS] paper_highlight_warm_hit_rate__cache_aware_joint : 0.571429
  [PASS] paper_highlight_warm_hit_rate__faascache : 0.542857
  [PASS] paper_highlight_warm_hit_rate__load_only : 0.200000
  [PASS] paper_highlight_image_cache_improvement : 0.485714
  [PASS] cache_aware_joint_ge_faascache_ge_load_only : ca=0.5714, fc=0.5429, lo=0.2000
  [PASS] paper_highlight_result_candidate_consistency : 1.0000
  [PASS] paper_highlight_request_decision_consistency : 1.0000
  [PASS] export_tables_have_no_index_column : no pandas index columns
=== 23 passed, 0 failed ===
data self-check: 23 / 23 PASS
```

## 4. 论文 demo 关键摘要（49 metric）

### 4.1 per-case 关键指标（3 case × 10 metric = 30 metric）

| metric | cache_aware_joint | faascache | load_only |
|--------|-------------------|-----------|-----------|
| `warm_hit_rate` | **0.5714** | 0.5429 | 0.2000 |
| `image_cache_hit_rate` | **0.8571** | 0.3714 | 0.3714 |
| `data_cache_hit_rate` | **0.8571** | 0.3714 | 0.3714 |
| `avg_latency` | **0.8547** | 1.4410 | 1.9095 |
| `p95_latency` | **3.166** | 5.162 | 5.162 |
| `total_cold_start_penalty` | **17.55** | 19.45 | 35.85 |
| `avg_r_cache` | 0.9714 | 0.9714 | 0.0000 |
| `avg_r_load` | 1.000 | 0.000 | 1.000 |
| `avg_r_desired` | 1.000 | 0.9714 | 1.000 |
| `eviction_count` | 12 | 13 | 27 |

### 4.2 策略相对改进（vs LoadOnly baseline）

| metric | value | note |
|--------|-------|------|
| `avg_latency_reduction__cache_aware_joint_vs_load_only` | 0.5524 | **论文 demo 关键数字**：CacheAwareJoint 延迟降 55% |
| `cold_start_penalty_reduction__cache_aware_joint_vs_load_only` | 0.5105 | **论文 demo 关键数字**：冷启动惩罚降 51% |
| `image_cache_hit_rate_improvement__cache_aware_joint_vs_load_only` | 0.4857 | **论文 demo 关键数字**：image 命中 +48.6 pp |
| `data_cache_hit_rate_improvement__cache_aware_joint_vs_load_only` | 0.4857 | **论文 demo 关键数字**：data 命中 +48.6 pp |

### 4.3 策略相对改进（vs FaasCache baseline）

| metric | value | note |
|--------|-------|------|
| `avg_latency_reduction__cache_aware_joint_vs_faascache` | 0.4068 | **论文 demo 关键证据**：cache-aware 调度胜出 |
| `image_cache_hit_rate_improvement__cache_aware_joint_vs_faascache` | 0.4857 | image 命中比 FaasCache 高 48.6 pp |
| `data_cache_hit_rate_improvement__cache_aware_joint_vs_faascache` | 0.4857 | data 命中比 FaasCache 高 48.6 pp |

### 4.4 R_cache vs R_load 主导分析（数值 metric）

| metric | value | note |
|--------|-------|------|
| `r_dominant_max__cache_aware_joint` | 1.000 | max(R_cache=0.97, R_load=1) = 1 |
| `r_dominant_source__cache_aware_joint` | 1.000 | 1=R_load 主导 |
| `r_dominant_max__faascache` | 0.971 | max(R_cache=0.97, R_load=0) = 0.97 |
| `r_dominant_source__faascache` | 0.000 | 0=R_cache 主导 |
| `r_dominant_max__load_only` | 1.000 | max(R_cache=0, R_load=1) = 1 |
| `r_dominant_source__load_only` | 1.000 | 1=R_load 主导 |

### 4.5 一致性

| metric | value | note |
|--------|-------|------|
| `result_candidate_consistency` | 1.0 | **论文 demo 关键证据**：105/105 match |
| `request_decision_consistency` | 1.0 | **论文 demo 关键证据**：105/105 match |

## 5. 4 张图说明

### fig01 — Three cache dimension hit rates by case（论文 demo 关键图）
- 3 副图：warm / image / data
- 每副图 3 柱：load_only（红）/ faascache（橙）/ cache_aware_joint（绿）
- **论文价值**：**image/data 维度 cache_aware_joint 0.857 vs 0.371**——cache-aware 调度让 image/data 命中率从 37% 翻到 86%，**FaasCache 在 image/data 上跟 LoadOnly 一样**（因为 FaasCache 调度不感知缓存位置）

### fig02 — Latency by case（论文 demo 关键图）
- 3 case × 2 柱：avg_latency（蓝）+ p95_latency（橙）
- **论文价值**：**cache_aware_joint 的 p95 也降**（5.16 → 3.17）—— tail latency 也改善，不只是平均值

### fig03 — R_cache vs R_load by case（论文 demo 关键图）
- 3 case × 3 柱：R_cache（蓝）/ R_load（橙）/ R_desired（灰）
- **论文价值**：**CacheAwareJoint 是唯一 R_cache + R_load 都 > 0 的策略**——`max` 公式生效，论文核心证据

### fig04 — Paper highlight metrics
- 分组横向条形：49 metric，分为 per-case outcome、R-cache/R-load、joint improvements、join consistency 四栏
- **论文价值**：
  - `request_decision_matched/total=105` + `result_candidate_matched/total=105` 直接对应 join 一致性
  - `total_cold_start_penalty: 35.85 / 19.45 / 17.55` 直接对应"冷启动惩罚降 51%"
  - `avg_latency_reduction__vs_load_only=0.5524` 对应"延迟降 55%"

## 6. 与 17 / 18 / 19 / 20 / 22 的对比

| 维度 | 17 cache | 18 decision | 19 scheduler | 20 autoscaling | 22 edge cache | **23 thesis** |
|------|----------|-------------|--------------|----------------|---------------|---------------|
| 验证目标 | 缓存策略 | 缓存决策 | 缓存调度 | 缓存扩缩容 | 边缘缓存调度 | **论文综合** |
| 跑 faas-sim? | ✗ | ✗ | ✓ | ✗ | ✗ | **✗ (整合)** |
| 多 case 对比? | ✗ | ✗ | ✓ (2) | ✗ | ✓ (2) | **✓ (3)** |
| 关键 join | eviction×state | decision×hint | probe×inv | decision×plan | result×candidate | **2 joins** |
| 缓存维度 | 1 (warm) | 1 (warm) | 1 (warm) | 1 (warm) | 3 (warm+image+data) | **3 (warm+image+data)** |
| R_cache vs R_load | ✗ | ✗ | ✗ | ✓ | ✗ | **✓ (3 case)** |
| 论文 chart | 柱+折 | 柱+条+柱+条 | 柱+柱+热力+条 | 折线+条+热力+条 | 柱+柱+条+条 | **柱+柱+柱+条** |

**23 的独特价值**：
- 第一个**论文级整合 demo**（整合 5 个样例的核心机制）
- 第一个 **3 case 对比**（baseline + cache-only + cache-aware joint）
- 第一个**用 R_cache vs R_load 3 case 验证 max 公式**生效
- 第一个**生成 Markdown 实验报告**（`thesis_experiment_report.md`）
- 第一个**同时有 2 个 join**（result×candidate + request×decision）

## 7. 输出文件清单

```
examples/23_thesis_experiment/
├── main.py                                # 入口：load 4 csv + run 3 cases + paper + md report + self-check
├── analysis.py                            # 4 summary + 2 join + paper + md report + self-check
├── loader.py                              # 4 csv 读取（profile / node / workload / cases）
├── models.py                              # FunctionProfile / NodeState / WorkloadEvent / ExperimentCase / 等
├── progress.py                            # tqdm 兼容
├── runner.py                              # ThesisExperimentRunner
├── simulator.py                           # trace-driven 实验模拟器
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── inputs/
│   ├── function_profile.csv              # 5 函数
│   ├── node_state.csv                    # 6 节点
│   ├── workload_trace.csv                 # 35 request
│   └── experiment_cases.csv              # 3 case (LoadOnly / FaasCache / CacheAwareJoint)
├── outputs/
│   ├── thesis_request_result.csv                 # 105 行
│   ├── thesis_control_decision.csv               # 105 个 control_decision
│   ├── thesis_candidate_score.csv                # 630 行
│   ├── thesis_eviction_event.csv                 # 驱逐事件
│   ├── thesis_policy_summary.csv                 # per-(case, policy)
│   ├── thesis_function_summary.csv               # per-(case, policy, function)
│   ├── thesis_phase_summary.csv                  # per-(case, policy, phase)
│   ├── thesis_control_summary.csv                # per-(case, policy, action, reason)
│   ├── thesis_baseline_comparison.csv            # 以 LoadOnly 为 baseline
│   ├── thesis_result_candidate_join.csv          # 论文 demo 关键证据
│   ├── thesis_request_decision_join.csv          # 论文 demo 关键证据
│   ├── thesis_paper_highlight.csv                # 49 metric + note
│   ├── thesis_experiment_self_check.csv          # 23 项数据自检
│   └── thesis_experiment_report.md               # Markdown 实验报告
└── figures/
    ├── fig01_three_cache_dim_hit_rates.png/pdf
    ├── fig02_latency_by_case.png/pdf
    ├── fig03_r_cache_vs_r_load_by_case.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **3 case 而非 2 case**：20 / 19 / 22 / 21 都是 2 case（baseline + 优化版），23 是**3 case**——LoadOnly（无 cache）+ FaasCache（cache-only，调度不感知）+ CacheAwareJoint（cache + 调度感知）。**3 case 验证的是"两层优化各自独立有效，组合后进一步提升"**——这是论文的核心论证结构。
- **LoadOnly = baseline, FaasCache = 中间态, CacheAwareJoint = 完整策略**：
  - LoadOnly 验证"完全无 cache"是性能底线
  - FaasCache 验证"只 cache 不调度"是 cache-only 基线
  - CacheAwareJoint 验证"cache + 调度"是完整策略
  - **cache_aware_joint_vs_faascache 的差距**证明"调度感知缓存"比"只 cache"更优
- **R_cache + R_load 组合而非加权**：23 用 max 组合（R_desired = max(R_cache, R_load)），**不是加权求和**。这是论文核心公式——保证两类需求任一满足都触发副本保护。
- **trace-driven 而非 faas-sim**：23 是 trace-driven 整合 demo（跟 17/18/20/21/22 同类），不跑 faas-sim。**目的是稳定生成论文实验 CSV 指标**，避免 faas-sim 接口变动破坏样例。
- **2 个 join 而非 1 个**：23 同时有 result×candidate（验证 cache_aware_joint 调度评分正确）+ request×decision（验证 R_cache/R_load/R_desired 一致）。**双 join 互相验证**——R_desired 必须跟 R_cache/R_load 一致，调度评分必须跟实际 cache_hit 一致。
- **Markdown 报告 + CSV 双输出**：23 是唯一生成 `.md` 报告的样例。报告汇总 policy summary + comparison + phase + paper highlight。**这是论文写作的原始素材**——直接复制粘贴到论文附录。
- **`r_dominant_max` + `r_dominant_source` 数值 metric**：23 把 `r_dominant_summary__xxx` 从 string 改为 2 个数值 metric（max + source），**让 fig04 能正确解析**。原来 string metric `r_cache=0.97, r_load=1.0, ...` 在 fig04 里 pd.to_numeric 解析成 NaN（fig04 跳过），**新数值 metric 让 fig04 能直接画**。
- **cache_aware_joint 必须 max-score，faascache / load_only 不要求**：23 的 result×candidate join 区分 3 case 的调度逻辑——cache_aware_joint 是评分驱动调度，必须选 max-score；faascache / load_only 是其他机制调度，**不要求 max-score 但要求 cache_hit / latency 一致**。这种"按 case 分别验证"是 23 跟 19/20/22 的关键差异。
- **诚实暴露 FaasCache 跟 LoadOnly 在 image/data 一样**：两者 image/data hit rate 都是 37.1%——因为 FaasCache **调度不感知 image/data cache 位置**，调度到哪里 cache 命中是随机的。这跟 18 的"决策不感知节点"类似——**cache 评分跟调度评分是两个独立维度**。
- **CacheAwareJoint 是唯一 R_cache + R_load 都 > 0 的策略**：图 03 一眼看出 R_cache / R_load / R_desired 三柱关系——`max` 公式让 cache_aware_joint 的 R_desired = 1.0（取 R_load），但 R_cache 也 = 0.97 同时保护冷启动价值。
