# 11_fault_model — 故障模型与请求成败分类

> **目标**：在 faas-sim 函数执行模拟器中引入确定性故障模型（节点不可用 / 副本错误 / 网络退化），
> 验证每条请求的故障分类、窗口判定一致性、以及 probe×invocation 派发一致性。

## 1. 复现步骤

```bash
# 1) 跑仿真（30 个请求，6 rps，触发 DeterministicFaultModel 的两个窗口事件）
python -u examples/11_fault_model/main.py

# 2) 跑绘图（4 张图：请求时间线 + 故障原因分布 + final_duration 散点 + 论文摘要）
python -u examples/11_fault_model/plot.py
```

输出：
- `outputs/`：12 个仿真/探针 metric + fault_events + probe_with_simtime + probe_fault_window_check + probe_invocation_join + fault_model_summary + fault_reason_distribution + **fault_model_paper_highlight** + **fault_model_self_check**
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 确定性故障模型（`fault_model.py`）

| 故障类型 | 描述 | 触发方式 | 影响 |
|---------|------|---------|------|
| `node_outage` | 节点不可用窗口 | simtime ∈ [1.00, 1.80]，target=server_0 | 硬故障，请求快速失败（0.03s） |
| `network_degradation` | 网络路径退化 | simtime ∈ [2.20, 3.60]，target=server_0 | 软故障，请求成功但 final_duration +0.45s |
| `replica_error` | 周期性副本错误 | request_id % 7 == 0（即 id=7,14,21,28） | 硬故障，请求快速失败（0.03s） |

判定优先级（`fault_model.decide`）：
1. **active event（node_outage）** 优先 → 硬故障失败
2. **replica_error** 周期性触发
3. **active event（network_degradation）** → 软故障成功但延时长
4. 正常请求 → 0.25s 完成

### 2.2 拓扑与调度

- **4-server 最小拓扑**（与 02/03/05/06/07/08 一致）：用 `ether.core` 直接构造 4 个 server 节点 + Docker Registry，
  构造一次复用。避免 `ether.scenarios.urbansensing` 连续实例化导致节点集不一致。
- **FixedNodeScheduler**：强制所有副本部署到 `server_0`，使故障窗口稳定作用于目标节点。

### 2.3 关键探针（沿用 02-10 的 invoke_dispatch_probe 模式）

`simulator.invoke` 入口写两条探针：
- `invoke_dispatch_probe`：`simtime` + `replica_id` + `request_id` + `expected_t_exec`（按 `decision.final_duration` 真实派发），
  用于 probe×invocation join 自洽检查。
- `fault_model_probe`：故障判定结果（`success` / `reason` / `base_duration` / `extra_delay` / `final_duration` / `failure_latency` / `active_fault`），
  用于故障类型统计和窗口命中。

## 3. 数据自检（11 项 PASS）

```
data self-check: 11 / 11 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `request_events_30` | 30 个请求全部完成 |
| 02 | `node_outage_failures_gt_zero` | 节点不可用窗口内有请求失败 |
| 03 | `replica_error_candidates_classified` | 4 个候选 id (7,14,21,28) 全部被 replica_error 或 node_outage 分类 |
| 04 | `replica_error_failures_at_least_3` | 至少 3 个候选 id 归到 replica_error（1 个可能被 node_outage 抢先） |
| 05 | `network_degradation_count_gt_zero` | 网络退化窗口内有请求被软故障 |
| 06 | `failure_count_explains_node_replica` | 失败数 == node_outage + replica_error（两类失败穷尽） |
| 07 | `node_outage_window_match_full` | 所有 node_outage 探针都落在 [1.0, 1.8] 窗口内 |
| 08 | `network_degradation_window_match_full` | 所有 network_degradation 探针都落在 [2.2, 3.6] 窗口内 |
| 09 | `normal_window_outside_full` | 所有 normal 探针都在窗口外 |
| 10 | `probe_invocation_t_exec_match_full` | simulator 派发的 final_duration 与 invocations.t_exec 100% 匹配 |
| 11 | `dispatch_probe_equals_invocations` | invoke_dispatch_probe 行数 == invocations 行数 |

**关于 check 03/04 的关键设计**：fault_model 的判定优先级是 active event 优先于 replica_error。
当候选 id=7（simtime=1.67）落在 node_outage 窗口 [1.0, 1.8] 内时，会被 node_outage 抢先判定失败。
因此 4 个候选 id 真正归到 replica_error 的数量 = 3（id=14, 21, 28），id=7 归到 node_outage。
check 03 验证 4 个候选 id 全部被 replica_error 或 node_outage 分类（=4），check 04 验证 replica_error >= 3。
这比简单断言 `replica_error == 4` 更准确，避免对判定优先级的过强假设。

## 4. 论文 demo 关键摘要（18 条）

`outputs/fault_model_paper_highlight.csv` 包含：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `request_events` | 30 | 触发请求总数 |
| `success_count` | 23 | 成功请求数（normal + network_degradation） |
| `failure_count` | 7 | 失败请求数（node_outage + replica_error） |
| `failure_rate` | 0.2333 | 失败率 |
| `node_outage_failures` | 4 | 节点不可用窗口失败数 |
| `replica_error_failures` | 3 | 周期性副本错误失败数 |
| `replica_error_candidates_classified` | 4 | 4 个候选 id 全部被 replica_error 或 node_outage 分类 |
| `network_degradation_count` | 7 | 网络退化软故障数 |
| `normal_count` | 16 | 正常请求数 |
| `avg_final_duration` | 0.3037 | 平均 final_duration（含故障延长） |
| `max_final_duration` | 0.70 | 最大 final_duration（= base + extra_delay） |
| `node_outage_window_match_rate` | 1.0 | node_outage 探针 100% 落在窗口内 |
| `network_degradation_window_match_rate` | 1.0 | network_degradation 探针 100% 落在窗口内 |
| `normal_window_match_rate` | 1.0 | normal 探针 100% 落在窗口外 |
| `probe_invocation_t_exec_match_rate` | 1.0 | probe 派发与 invocations 记录 100% 匹配 |
| `fault_event_total` | 2 | 故障事件数（节点 + 网络） |
| `fault_window_total_seconds` | 2.2 | 故障窗口总时长（0.8 + 1.4） |
| `dispatch_probe_count` | 30 | invoke_dispatch_probe 行数 |

## 5. 4 张图说明

### fig01 — Request Timeline vs Fault Windows（论文 demo 关键图）
- x 轴：simtime，y 轴：请求序号（按 simtime 升序）
- 颜色：reason（绿=normal, 紫=replica_error, 红=node_outage, 橙=network_degradation）
- 红色阴影 = node_outage 窗口 [1.0, 1.8]
- 橙色阴影 = network_degradation 窗口 [2.2, 3.6]
- **论文价值**：视觉证明所有 node_outage / network_degradation 请求严格落在故障窗口内，验证 fault_model 的窗口判定是精确的。

### fig02 — Fault Reason Distribution
- 4 个 reason 的请求数柱状图，颜色与 fig01 一致
- **论文价值**：一眼看出三类故障类型的相对频率。

### fig03 — Per-Request final_duration vs Simtime
- x 轴：simtime，y 轴：final_duration
- 三条参考线：base_duration=0.25s（绿）、base+extra_delay=0.70s（橙）、failure_latency=0.03s（红）
- **论文价值**：直观显示网络退化把请求时长从 0.25s 放大到 0.70s，失败请求被压到 0.03s。

### fig04 — Paper Highlight Metrics
- 论文 demo 关键摘要指标的横向条形图（17 个 metric）
- **论文价值**：所有 demo 数字集中展示，便于图表引用。

## 6. 与 02-10 的 demo 价值对比

| 维度 | 02 LB | 05 scale | 06 trig | 08 deg | **11 fault** |
|------|-------|---------|---------|--------|------------|
| 验证目标 | 路由均衡 | 副本伸缩 | 请求生成 | 性能退化 | **故障判定 + 窗口一致性** |
| 探针 | dispatch_probe | dispatch_probe | dispatch_probe | dispatch_probe | **dispatch_probe + fault_probe** |
| 关键 join | route×probe×inv | — | — | probe×degradation | **probe×fault_events×invocation** |
| 核心数字 | balance_std=0 | scale_min→max | rps=profile | slowdown_pct | **failure_rate=0.23, window_match=1.0** |
| 论文 chart | 阶梯图 + 分布 | 副本数曲线 | 到达曲线 | 退化曲线 | **窗口阴影散点 + duration 散点** |

**11 的独特价值**：11 是 02-10 中**唯一一个**用「时间窗口 + 探针 + 判定优先级」三重机制共同验证故障模型的样例。
其他样例关注"请求发生了什么"，11 关注"请求被分类为什么，且分类是否与仿真事件时间线严格一致"。

## 7. 输出文件清单

```
examples/11_fault_model/
├── main.py                                # 4-server 拓扑 + FixedNodeScheduler + 故障 Benchmark
├── fault_model.py                         # DeterministicFaultModel + FaultEvent + FaultDecision
├── scheduler.py                           # FixedNodeScheduler（强制 server_0）
├── simulator.py                           # FaultModelFunctionSimulator + invoke_dispatch_probe
├── analysis.py                            # 13 metrics + probe×simtime + 窗口命中 + paper_highlight + self_check
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
│   ├── invoke_dispatch_probe.csv          # 新增：invoke 入口探针（simtime + replica_id）
│   ├── fault_model_probe.csv              # 故障判定探针
│   ├── fault_timeline.csv                 # 故障事件时间线
│   ├── fault_events.csv                   # 故障事件定义
│   ├── probe_with_simtime.csv             # probe 重建 simtime
│   ├── probe_fault_window_check.csv       # probe × fault_events 窗口命中
│   ├── probe_invocation_join.csv          # probe × invocations 关联
│   ├── fault_model_summary.csv            # 故障摘要
│   ├── fault_reason_distribution.csv      # 故障原因分布
│   ├── fault_model_paper_highlight.csv    # 论文 demo 关键摘要
│   └── fault_model_self_check.csv         # 11 项数据自检
└── figures/
    ├── fig01_request_timeline_with_fault_windows.png/pdf
    ├── fig02_fault_reason_distribution.png/pdf
    ├── fig03_per_request_final_duration.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **确定 vs 随机故障**：用确定性故障事件（固定 start_time / end_time）而非随机分布，便于样例复现和结果解释。
  论文 demo 需要"跑两次结果一致"的可重现性。
- **故障判定与仿真解耦**：fault_model 不修改 faas-sim 核心代码，而是通过独立模块 + 自定义指标实现。
  这保留了原框架的纯洁性，也方便替换为更复杂的故障模型（如基于历史 trace 的故障注入）。
- **窗口 vs 探针的双向验证**：用 `probe_fault_window_check.csv` 反向验证「每个标记为 node_outage 的请求都落在 [1.0, 1.8] 窗口内」，
  而不是只检查「窗口内有多少请求」。这种"双向"验证更接近论文里"假设 H 在所有样本中成立"的标准。
- **判定优先级透明化**：当候选 id=7 因落在 node_outage 窗口内而被抢先判定时，self_check 03/04 的拆分
  显式承认"4 个候选 id 中有 3 个归到 replica_error、1 个被 node_outage 覆盖"，避免对 fault_model 行为的过强假设。
