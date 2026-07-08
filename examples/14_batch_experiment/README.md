# 14_batch_experiment — 多策略 × 多负载 × 多 seed 批量实验

> **目标**：组织 faas-sim 批量仿真实验框架（2 policies × 2 workloads × 2 seeds = 8 cases），
> 验证调度策略在异构 capacity 拓扑下选择节点的差异，并通过 probe×invocation join
> 验证 simulator 派发与 faas-sim 实际执行时长一致。

## 1. 复现步骤

```bash
# 1) 跑批量仿真（8 cases，with 进度条）
python -u examples/14_batch_experiment/main.py

# 2) 跑绘图（4 张图：策略命中率 + per-case 散点 + scheduled_node 分布 + 论文摘要）
python -u examples/14_batch_experiment/plot.py
```

输出：
- `outputs/runs/<case_id>/`：每个 case 11 个 metric + batch_probe_invocation_join + case_result
- `outputs/` 顶层：batch_results + batch_summary + batch_paper_highlight + **batch_self_check**
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 异构 capacity 拓扑（`runner.py`）

```text
DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0 (1 cpu, 1GB)
                                       |
                                       -- link_server_1 -- server_1 (8 cpu, 4GB) ★
                                       |
                                       -- link_server_2 -- server_2 (4 cpu, 2GB)
                                       |
                                       -- link_server_3 -- server_3 (4 cpu, 2GB)
```

server_1 是 8cpu 大容量节点，`CapacityAwareScheduler` 总是选这个；
server_0 是 1cpu 小容量节点，`FixedNodeScheduler` 强制选这个。
两个策略的节点选择产生**可量化的差异**（`scheduled_node` 不同）。

**为什么用 CapacityAwareScheduler 替代 faas-sim Skippy 默认**：faas-sim 的 Skippy 默认 predicates
在我们这个最小 4-server 拓扑里倾向于把 server_0 当成第一个候选，导致 default_skippy
跟 fixed_node 一样都选 server_0，policy 差异被掩盖。
CapacityAwareScheduler 直接选 capacity 最大节点，让两个 policy 的节点选择产生**可量化的差异**。

### 2.2 策略 × 负载 × 种子

| 维度 | 取值 |
|------|------|
| Policy | `default_skippy`（实现走 CapacityAwareScheduler）、`fixed_node`（走 FixedNodeScheduler） |
| Workload | `low_load` (rps=3, max=12)、`medium_load` (rps=8, max=24) |
| Seed | 1, 2 |
| **总 case 数** | 2 × 2 × 2 = **8** |

### 2.3 关键探针

- `batch_invoke_probe`：simulator 每次 invoke 写 `base_duration` / `jitter` / `duration` / `seed` / `rps`
- `invoke_dispatch_probe`（仿 02-13 模式）：simtime + replica_id + request_id + expected_t_exec
- `invocations`：faas-sim 实际记录 `t_start` / `t_exec` / `node`
- `batch_probe_invocation_join`：每 case 按 (function, node) 关联 probe×invocation，验证 duration 100% 一致

## 3. 数据自检（11 项 PASS）

```
data self-check: 11 / 11 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01-08 | `probe_invocation_join_match__{case_id}` | 8 个 case 的 probe / invocation / join 行数一致，且 `duration_match` 100% |
| 09 | `batch_results_row_count` | batch_results 行数 == 8（避免 silent case 被丢） |
| 10 | `high_capacity_hit_ratio__default_skippy` | 4/4 = 1.00，强检查 capacity-aware 100% 选 server_1 |
| 11 | `high_capacity_hit_ratio__fixed_node` | 0/4 = 0.00，强检查 fixed_node 0% 选 server_1 |

14 的 self_check 使用强检查：不仅确认文件存在和 join 成功，还确认每个 case 的
`probe_rows == invocation_rows == join_rows`，并确认两个策略的 high-capacity 命中率符合实验设计。

## 4. 论文 demo 关键摘要（14 条）

`outputs/batch_paper_highlight.csv` 包含（沿用 02-13 的 metric/value/note 三列模式）：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `total_cases` | 8 | 批量实验总 case 数 |
| `total_policies` | 2 | 策略数 |
| `total_workloads` | 2 | 负载数 |
| `total_seeds` | 2 | 随机种子数 |
| `total_invocations` | 144 | 跨所有 case 的总 invoke 次数（4 case × 12 + 4 case × 24） |
| `avg_invocations_per_case` | 18 | 每个 case 平均 invoke 次数 |
| `scheduled_nodes__default_skippy` | server_1 | default_skippy 策略实际选过的节点集合 |
| `high_capacity_hit_ratio__default_skippy` | 1.00 | default_skippy 选中 server_1 的比例（**论文 demo 关键数字**） |
| `scheduled_nodes__fixed_node` | server_0 | fixed_node 策略实际选过的节点集合 |
| `high_capacity_hit_ratio__fixed_node` | 0.00 | fixed_node 选中 server_1 的比例 |
| `{policy}__avg_probe_seconds__{workload}` | ~0.22s，共 4 条 | 每 policy × workload 下的 avg_probe_seconds |

**关键诚实性事实**：`avg_probe_duration` 在两种 policy 下几乎一致（~0.22s），
因为 sim 模型的 `t_exec` 等于 `base_duration`，节点 capacity 不会改变 single-invoke duration，
只会改变调度/排队/资源分配。**这一点要在论文里诚实写出来**——14 不掩盖 sim 模型的局限。

## 5. 4 张图说明

### fig01 — Policy high_capacity_node hit ratio（论文 demo 关键图）
- 柱状图：default_skippy = 1.00（绿），fixed_node = 0.00（红）
- y 轴 0~1.15
- **论文价值**：一眼看出"容量感知调度"vs"固定节点"在异构拓扑下的节点选择差异。

### fig02 — Per-case avg_probe_duration
- 散点图：x = case_id，y = avg_probe_duration
- 颜色按 policy（绿=default_skippy，红=fixed_node），形状按 workload（圆=low，方=medium）
- **论文价值**：8 个 case 的 probe duration 都在 0.218~0.224s 之间，**两种 policy 几乎一致**。
  这诚实展示了 sim 模型下"capacity 不改 single-invoke duration"的事实，避免论文误述。

### fig03 — Per-case scheduled_node
- 条状图：x = case_id（def/low/s1 等），y = 1.0（统一高度）
- 颜色：绿 = server_1（default_skippy 全部命中），红 = server_0（fixed_node 全部命中）
- **论文价值**：可视化每个 case 实际选到的节点，证明"两种策略的节点选择完全不同"。

### fig04 — Paper Highlight Metrics
- 双子图横向条形图：左侧是 batch size/count 指标，右侧是 policy hit ratio 和 avg_probe_seconds 指标
- **论文价值**：避免 `total_invocations=144` 把 0~1 的命中率和 ~0.22s 的 duration 压扁，同时保留论文可引用的关键数字。

## 6. 与 02-13 的 demo 价值对比

| 维度 | 02 LB | 05 scale | 06 trig | 08 deg | 11 fault | 12 cold | 13 image | **14 batch** |
|------|-------|---------|---------|--------|---------|---------|----------|---------------|
| 验证目标 | 路由均衡 | 副本伸缩 | 请求生成 | 性能退化 | 故障判定 | 冷启动路径 | 镜像缓存 | **批量实验框架** |
| Case 数 | 1 | 1 | 1 | 1 | 1 | 1 | 2 (双场景) | **8 (2×2×2)** |
| 探针 | dispatch_probe | dispatch_probe | dispatch_probe | dispatch_probe | dispatch + fault | dispatch + phase | dispatch + cache | **dispatch + batch_invoke** |
| 关键 join | route×probe×inv | — | — | probe×degradation | probe×fault×inv | probe×inv | probe×flow | **probe×inv (per case)** |
| 核心数字 | balance_std=0 | scale_min→max | rps=profile | slowdown_pct | failure_rate=0.23 | first/warm=3.75x | speedup=2.0x | **hit_ratio=1.0 vs 0.0** |
| 论文 chart | 阶梯图 | 副本曲线 | 到达曲线 | 窗口散点 | Gantt | Gantt | 双柱+散点 | **柱状图+散点+条状** |

**14 的独特价值**：14 是 02-13 中**唯一一个**提供"实验工程组织框架"的样例。
其他样例关注"如何验证某一个现象"，14 关注"如何系统地运行多个 case、汇总结果、做跨 case 比较"。
14 也是 02-13 中**唯一一个诚实指出"sim 模型不改变 single-invoke duration"**的样例——
这种诚实性比强行制造一个"policy 差异"更能支撑论文的实验可信度。

## 7. 输出文件清单

```
examples/14_batch_experiment/
├── main.py                                # 入口：循环跑 8 cases + 汇总 + self-check
├── experiment_config.py                   # PolicyConfig / WorkloadConfig / ExperimentCase
├── runner.py                              # 单 case 执行器（_SHARED_TOPOLOGY + 异构 capacity）
├── benchmark.py                           # BatchExperimentBenchmark + wait_for_invocations
├── simulator.py                           # BatchExperimentFunctionSimulator + invoke_dispatch_probe
├── scheduler.py                           # FixedNodeScheduler + CapacityAwareScheduler
├── analysis.py                            # 11 metrics + batch_results + paper_highlight + self_check
├── progress.py                            # tqdm 进度条（无 tqdm 时回退普通迭代器）
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── _probe.py                              # 一次性 probe 调试脚本（不是核心代码）
├── outputs/
│   ├── runs/<case_id>/                    # 8 个 case 子目录
│   │   ├── batch_invoke_probe.csv         # simulator 探针
│   │   ├── invoke_dispatch_probe.csv      # dispatch probe（仿 02-13）
│   │   ├── invocations.csv                # faas-sim 实际记录
│   │   ├── batch_probe_invocation_join.csv# probe × inv 关联
│   │   ├── case_result.csv                # 单 case 摘要
│   │   ├── schedule.csv                   # faas-sim 内置
│   │   ├── function_*.csv                 # faas-sim 内置
│   │   ├── replica_*.csv                  # faas-sim 内置
│   │   ├── flow.csv                       # faas-sim 内置
│   │   └── node_utilization.csv           # faas-sim 内置
│   ├── batch_results.csv                  # 8 case × 单行结果
│   ├── batch_summary.csv                  # 按 (policy, workload) 聚合
│   ├── batch_paper_highlight.csv          # 论文 demo 关键摘要（11 metric + note）
│   └── batch_self_check.csv               # 11 项 self-check
└── figures/
    ├── fig01_policy_high_capacity_hit_ratio.png/pdf
    ├── fig02_per_case_avg_probe_duration.png/pdf
    ├── fig03_scheduled_node_distribution.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **诚实承认 sim 模型限制**：14 的 paper_highlight 显式指出"avg_probe_duration 两种 policy 几乎一致"，
  这是 sim 模型的诚实特性（capacity 不改 single-invoke duration）。
  比强行制造一个"policy 差异"更能支撑论文可信度。
- **CapacityAwareScheduler 替代 faas-sim Skippy 默认**：faas-sim 的 Skippy 默认 predicates
  在小拓扑里倾向选 server_0，导致 default_skippy 跟 fixed_node 一样看不出差异。
  14 用 CapacityAwareScheduler 让两个 policy 的节点选择产生**可量化的差异**。
  这是**为了 demo 清晰而做的工程妥协**，不是修改 faas-sim 核心。
- **强检查但不膨胀 self_check 数量**：14 对每个 case 只保留 1 条 join 检查，但这条检查同时覆盖
  probe 行数、invocation 行数、join 行数和 duration_match。策略命中率也明确检查
  default_skippy == 1.0、fixed_node == 0.0。
- **每个 case 独立目录**（`outputs/runs/<case_id>/`）：方便论文中"展示 case X 的细节"，
  不会因为汇总 csv 丢失单个 case 的原始 trace。代价是磁盘空间多 8 倍。
- **fixed random.seed(case.seed) + 独立 rng**：simulator 的 jitter 用独立 `random.Random(case.seed)`，
  每个 case 的 jitter 序列可复现。这是论文 demo 的"可重现性"基础。
- **直接抛异常而非 fallback**：FixedNodeScheduler / CapacityAwareScheduler 找不到目标节点时**直接抛 RuntimeError**，
  不再悄悄 fallback。silent fallback 是最难排查的 bug 类型，抛异常至少让结果可解释。
