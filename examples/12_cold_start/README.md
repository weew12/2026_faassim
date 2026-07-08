# 12_cold_start — 冷启动路径阶段分解

> **目标**：将函数副本从创建到可用的过程拆分为 deploy / startup / setup / first_invoke / warm_invoke 五个阶段，
> 验证冷启动激活路径 (deploy+startup+setup) 与首次请求路径 (cold_activation+first_invoke) 的分解一致性，
> 以及 probe×invocation 派发时长自洽。

## 1. 复现步骤

```bash
# 1) 跑仿真（3 个请求：first_invoke + 2× warm_invoke，5 个 phase 全部触发）
python -u examples/12_cold_start/main.py

# 2) 跑绘图（4 张图：Gantt + first vs warm + per-phase 散点 + 论文摘要）
python -u examples/12_cold_start/plot.py
```

输出：
- `outputs/`：11 个 faas-sim 内置 metric（含 invoke_dispatch_probe） + cold_start_phase_summary + cold_start_replica_path_summary + cold_start_warm_cold_compare + cold_start_probe_invocation_join + **cold_start_paper_highlight** + **cold_start_self_check**
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 冷启动阶段模型（`cold_start_model.py`）

| 阶段 | 默认耗时 | 描述 |
|------|---------|------|
| `startup` | 0.75s | 容器/运行时启动 |
| `setup` | 0.55s | 函数业务初始化 |
| `first_invoke` | 0.30s | 副本首次请求执行 |
| `warm_invoke` | 0.08s | 后续热路径请求执行 |
| `deploy` | 实测 ≈ 4.0s | docker.pull 实际拉取时间（受镜像大小和拓扑影响） |

关键路径定义：
- **cold_activation_duration** = deploy + startup + setup
- **first_request_path_duration** = cold_activation + first_invoke

### 2.2 拓扑与请求

- **4-server 最小拓扑**（与 02/03/05/06/07/08/11 一致）：`ether.core` 直接构造 4 个 server + Docker Registry，构造一次复用。
- **3 个请求**（2 rps 触发）：
  - id=1 → first_invoke（同一副本首次请求，走 0.30s 慢路径）
  - id=2,3 → warm_invoke（同一副本后续请求，走 0.08s 快路径）

### 2.3 关键探针（沿用 02-11 的 invoke_dispatch_probe 模式）

`simulator.invoke` 入口写两条探针：
- `invoke_dispatch_probe`：`simtime` + `replica_id` + `request_id` + `expected_t_exec`（按 first/warm 阶段时长真实派发），用于 probe×invocation join 自洽检查。
- `cold_start_probe`：阶段事件（`phase` + `phase_start` + `phase_finish` + `phase_duration` + `request_id`），用于阶段耗时统计和 Gantt 还原。

## 3. 数据自检（11 项 PASS）

```
data self-check: 11 / 11 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `five_phases_present` | 5 个 phase 全部出现（deploy/startup/setup/first_invoke/warm_invoke） |
| 02 | `request_events_equals_3` | 3 个请求全部完成 |
| 03 | `startup_equals_0_75` | startup 总耗时 = 0.75s（固定配置） |
| 04 | `setup_equals_0_55` | setup 总耗时 = 0.55s（固定配置） |
| 05 | `first_invoke_avg_equals_0_30` | first_invoke 平均耗时 = 0.30s |
| 06 | `warm_invoke_avg_equals_0_08` | warm_invoke 平均耗时 = 0.08s |
| 07 | `cold_activation_equals_sum` | cold_activation == deploy + startup + setup（恒等式） |
| 08 | `first_request_path_equals_cold_plus_first` | first_request_path == cold_activation + first_invoke（恒等式） |
| 09 | `first_warm_speedup_3_75x` | first/warm speedup = 3.75x（0.30/0.08） |
| 10 | `probe_invocation_t_exec_match_full` | simulator 派发时长与 invocations.t_exec 100% 匹配 |
| 11 | `dispatch_probe_equals_invocations` | invoke_dispatch_probe 行数 == invocations 行数 (3 == 3) |

**关键设计**：self_check 故意不用绝对值断言 cold_activation = 2.10s，因为 deploy 阶段受 docker.pull 实际拉取时间影响（在 4-server 拓扑下测得 ≈ 4.0s）。改用恒等式 `cold_activation == deploy + startup + setup` 验证阶段分解的正确性，这是更鲁棒的不变量。

## 4. 论文 demo 关键摘要（20 条）

`outputs/cold_start_paper_highlight.csv` 包含：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `phase_events_total` | 6 | 5 个 phase 触发的事件总数（deploy+startup+setup+first_invoke+2×warm_invoke） |
| `deploy_events` | 1 | deploy 阶段事件数 |
| `startup_events` | 1 | startup 阶段事件数 |
| `setup_events` | 1 | setup 阶段事件数 |
| `first_invoke_events` | 1 | first_invoke 阶段事件数 |
| `warm_invoke_events` | 2 | warm_invoke 阶段事件数 |
| `deploy_total_duration` | ~4.0s | deploy 总耗时（含 docker.pull 实际拉取时间） |
| `startup_total_duration` | 0.75s | startup 总耗时 |
| `setup_total_duration` | 0.55s | setup 总耗时 |
| `first_invoke_total_duration` | 0.30s | first_invoke 总耗时 |
| `warm_invoke_total_duration` | 0.16s | warm_invoke 总耗时（2 个请求） |
| `cold_activation_duration` | ~5.30s | 冷启动激活时长 = deploy + startup + setup |
| `first_request_path_duration` | ~5.60s | 首次请求路径时长 = cold_activation + first_invoke |
| `first_invoke_avg` | 0.30s | first_invoke 平均耗时 |
| `warm_invoke_avg` | 0.08s | warm_invoke 平均耗时 |
| `first_warm_speedup_ratio` | 3.75x | first/warm speedup 比值（**论文 demo 关键数字**） |
| `cold_warm_speedup_ratio` | ~66x | cold_activation/warm speedup 比值 |
| `probe_invocation_t_exec_match_rate` | 1.0 | probe 派发与 invocations 记录 100% 匹配 |
| `dispatch_probe_count` | 3 | invoke_dispatch_probe 行数 |
| `invocation_count` | 3 | invocations 行数 |

## 5. 4 张图说明

### fig01 — Cold Start Path Gantt（论文 demo 关键图）
- y 轴：5 个 phase（deploy / startup / setup / first_invoke / warm_invoke）
- x 轴：simtime
- 横向条：每个 phase 的 [phase_start, phase_finish] 区间，标 duration 数字
- 浅蓝阴影 = cold_activation 范围（deploy+startup+setup）
- 虚线标出 cold_activation 结束位置
- **论文价值**：一眼看出冷启动路径的 5 个阶段分解，cold_activation 范围清晰可见，warm_invoke 远在 cold_activation 之后。

### fig02 — first_invoke vs warm_invoke（3.75x speedup）
- 柱状图：first_invoke 0.30s vs warm_invoke 0.08s
- 标题直接显示 speedup 倍数
- **论文价值**：3.75x speedup 是冷启动感知调度 / 预热策略的核心论点。

### fig03 — Per-Phase phase_duration vs Simtime
- x 轴：phase_start simtime
- y 轴：phase_duration
- 颜色按 phase，参考线标固定值（startup/setup/first_invoke/warm_invoke）
- **论文价值**：直观显示 deploy 受 docker.pull 拉取时间影响（4.0s 远大于其他固定阶段），其他 4 个 phase 是稳定配置值。

### fig04 — Paper Highlight Metrics
- 论文 demo 关键摘要指标的横向条形图（20 个 metric）
- **论文价值**：所有 demo 数字集中展示，便于图表引用。cold_warm_speedup_ratio 66.22x 是最显眼的 bar。

## 6. 与 02-11 的 demo 价值对比

| 维度 | 02 LB | 05 scale | 06 trig | 08 deg | 11 fault | **12 cold_start** |
|------|-------|---------|---------|--------|---------|------------------|
| 验证目标 | 路由均衡 | 副本伸缩 | 请求生成 | 性能退化 | 故障判定 | **冷启动路径分解** |
| 探针 | dispatch_probe | dispatch_probe | dispatch_probe | dispatch_probe | dispatch + fault | **dispatch + phase** |
| 关键 join | route×probe×inv | — | — | probe×degradation | probe×fault×inv | **probe×inv（按 phase）** |
| 核心数字 | balance_std=0 | scale_min→max | rps=profile | slowdown_pct | failure_rate=0.23 | **first/warm=3.75x** |
| 论文 chart | 阶梯图 | 副本数曲线 | 到达曲线 | 退化曲线 | 窗口阴影散点 | **Gantt + 对比柱状图** |

**12 的独特价值**：12 是 02-11 中**唯一一个**用「5 阶段 + 首次 vs 热路径」双重分解刻画冷启动路径的样例。
其他样例关注"请求发生了什么"，12 关注"副本从创建到可用经历了什么阶段，每个阶段耗时多少，以及首次请求 vs 后续请求的差距"。
12 的 paper_highlight 里 `first_warm_speedup_ratio = 3.75x` 是冷启动感知调度/预热策略的**最直接证据**——
只有当 first_invoke 显著慢于 warm_invoke 时，缓存预热才有意义。

## 7. 输出文件清单

```
examples/12_cold_start/
├── main.py                                # 4-server 拓扑 + ColdStartBenchmark
├── cold_start_model.py                    # ColdStartModel + ColdStartPhaseConfig
├── simulator.py                           # ColdStartFunctionSimulator + invoke_dispatch_probe
├── analysis.py                            # 11 metrics + phase_summary + warm_cold_compare + paper_highlight + self_check
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── outputs/
│   ├── invocations.csv                    # faas-sim 内置
│   ├── schedule.csv                       # faas-sim 内置
│   ├── function_deployments.csv           # faas-sim 内置
│   ├── function_replicas.csv              # faas-sim 内置
│   ├── replica_deployment.csv             # faas-sim 内置
│   ├── flow.csv                           # faas-sim 内置
│   ├── function_utilization.csv           # faas-sim 内置
│   ├── node_utilization.csv               # faas-sim 内置
│   ├── function_deployment_lifecycle.csv  # faas-sim 内置
│   ├── invoke_dispatch_probe.csv          # 新增：invoke 入口探针（simtime + replica_id + phase）
│   ├── cold_start_probe.csv               # 5 个 phase 阶段事件
│   ├── cold_start_phase_summary.csv       # 按 phase 分组的事件数/平均/最小/最大耗时
│   ├── cold_start_replica_path_summary.csv# 副本冷启动路径汇总
│   ├── cold_start_warm_cold_compare.csv   # first vs warm 对比
│   ├── cold_start_probe_invocation_join.csv# probe × invocations 关联
│   ├── cold_start_paper_highlight.csv     # 论文 demo 关键摘要
│   └── cold_start_self_check.csv          # 11 项数据自检
└── figures/
    ├── fig01_cold_start_path_gantt.png/pdf
    ├── fig02_first_vs_warm_compare.png/pdf
    ├── fig03_per_request_phase_duration.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **绝对值 vs 恒等式**：self_check 故意不用绝对值断言 `cold_activation = 2.10s`，因为 deploy 阶段受 docker.pull
  实际拉取时间影响（4-server 拓扑下 ≈ 4.0s，UrbanSensingScenario 下 ≈ 0.8s）。改用恒等式
  `cold_activation == deploy + startup + setup` 验证阶段分解的正确性，这是拓扑无关的不变量。
- **first_invoke_seen 状态用实例变量**：`ColdStartFunctionSimulator` 为每个 simulator 实例维护已见过的 replica id 集合，
  用于区分 first_invoke 与 warm_invoke，避免多个仿真实例复用时出现状态污染。
- **deploy 阶段不固定**：故意让 deploy 走真实的 `docker.pull()`，让 demo 真实反映 faas-sim 的镜像拉取开销。
  这也是 paper_highlight 中 cold_warm_speedup 数字会随拓扑变化的原因。
- **5 阶段 vs 2 阶段**：选择"5 阶段"（deploy/startup/setup/first_invoke/warm_invoke）而不是"2 阶段"（cold/warm），
  是因为 5 阶段能让论文 demo 展示"冷启动激活路径"（deploy+startup+setup）和"首次请求路径"
  （cold_activation+first_invoke）的细分，揭示缓存命中主要影响的是 deploy 阶段。
