# 15_experiment_analysis — 批量实验结果聚合分析

> **目标**：从 14_batch_experiment 的 outputs 统一读取多 run 的 CSV，
> 生成 run-level 单行指标、按 (policy, workload) 聚合摘要、策略对比表、
> 论文 demo 关键摘要（含 speedup_ratio 和 relative change）和数据自检段，
> 自动生成 Markdown 分析报告。

## 1. 复现步骤

```bash
# 1) 跑 14 的批量实验（必须先有 outputs/runs/<case_id>/）
python -u examples/14_batch_experiment/main.py

# 2) 跑 15 的聚合分析（自动读 14 的 outputs）
python -u examples/15_experiment_analysis/main.py

# 3) 跑绘图（4 张图：per-run 散点 + policy comparison + hit ratio + 论文摘要）
python -u examples/15_experiment_analysis/plot.py
```

也可以指定输入输出目录：
```bash
python -u examples/15_experiment_analysis/main.py --input-dir examples/14_batch_experiment/outputs
python -u examples/15_experiment_analysis/main.py --output-dir examples/15_experiment_analysis/outputs
```

输出：
- `outputs/`：5 个 CSV + 1 个 Markdown 报告 + **self_check.csv**
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 14 → 15 工作流

15 不是单独的仿真样例，而是 14 的**聚合分析器**。15 默认从 14 的 outputs/ 读，缺省回退到 sample_results：

```text
14_batch_experiment 跑 8 个 case
        ↓
   outputs/runs/<case_id>/{batch_invoke_probe, invocations, schedule, flow, ...}.csv
        ↓
15_experiment_analysis 统一读 + 聚合
        ↓
   experiment_run_metrics.csv           # 每 case 单行
   experiment_summary.csv               # 按 (policy, workload) 聚合
   experiment_policy_comparison.csv     # 其他 policy vs default_skippy baseline
   experiment_paper_highlight.csv       # 论文 demo 关键摘要
   experiment_analysis_report.md        # Markdown 报告
   self_check.csv                       # 11 项数据自检
```

### 2.2 模块化设计

| 文件 | 职责 |
|------|------|
| `config.py` | 输入/输出目录解析、source_name 标签 |
| `loaders.py` | 自动发现 run 目录（支持 `runs/<case_id>/` 和扁平 `<case_id>/` 两种结构）、安全读 CSV |
| `metrics.py` | 单 run → 单行指标（case_id / policy / workload / seed / scheduled_node / probe_avg_duration / ...） |
| `aggregation.py` | run_metrics → summary → policy_comparison → paper_highlight |
| `self_check.py` | 11 项数据自洽检查 + 写 self_check.csv |
| `report.py` | 生成 Markdown 分析报告（6 节） |
| `main.py` | 入口：调 loaders → metrics → aggregation → self_check → report |

### 2.3 关键检查

15 的 self_check（11 项）覆盖：
- run_metrics 行数、probe/invocation 总数一致性、每 run probe/invocation 行数一致性、summary 行数、comparison 行数
- paper highlight 的 high_capacity_hit_ratio 跟 run_metrics 一致
- summary 跟 paper highlight 的 avg_probe_seconds 完全一致（4 个 cell）

## 3. 数据自检（11 项 PASS）

```
data self-check: 11 / 11 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `run_metrics_min_rows` | run_metrics 行数 >= 2（应 == 8） |
| 02 | `total_probe_equals_total_invocation` | total_probes == total_invocations（144 == 144） |
| 03 | `per_run_probe_equals_invocation` | 每个 run 的 probe_events == invocation_events |
| 04 | `summary_row_count` | summary 行数 == policies × workloads（2×2=4） |
| 05 | `comparison_row_count` | comparison 行数 == (policies-1) × workloads（baseline 自身被跳过，1×2=2） |
| 06 | `high_capacity_hit_ratio__default_skippy` | paper highlight 值 == 实际 run_metrics 计算，且符合预期（4/4=1.00） |
| 07 | `high_capacity_hit_ratio__fixed_node` | 同上，且符合预期（0/4=0.00） |
| 08-11 | `avg_probe_seconds_consistency__{policy}__{workload}` | 4 个 cell 的 summary vs highlight 完全一致 |

**关键设计**：15 的 self_check 比 14 多了"summary vs highlight 一致性"检查。
这种**跨表一致性检查**是聚合分析样例的核心——保证 paper highlight 里的数字
跟聚合摘要的源数据完全一致，避免论文里出现"两个表对不上"的低级错误。

## 4. 论文 demo 关键摘要（19 条）

`outputs/experiment_paper_highlight.csv` 包含（沿用 02-14 的 metric/value/note 三列模式）：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `total_runs` | 8 | 分析的 run 总数 |
| `total_policies` | 2 | 策略数 |
| `total_workloads` | 2 | 负载数 |
| `total_seeds` | 2 | 随机种子数 |
| `total_invocations` | 144 | 跨所有 run 的总 invoke 次数 |
| `total_probes` | 144 | 跨所有 run 的总 probe 次数（应 == total_invocations） |
| `comparison_row_count` | 2 | experiment_policy_comparison.csv 行数 |
| `scheduled_nodes__default_skippy` | server_1 | default_skippy 实际选过的节点集合 |
| `high_capacity_hit_ratio__default_skippy` | 1.00 | default_skippy 选中 server_1 的比例 |
| `scheduled_nodes__fixed_node` | server_0 | fixed_node 实际选过的节点集合 |
| `high_capacity_hit_ratio__fixed_node` | 0.00 | fixed_node 选中 server_1 的比例 |
| `{policy}__avg_probe_seconds__{workload}` | ~0.22s | 每 policy × workload 下的 mean_probe_avg_duration |
| `speedup_ratio_fixed_over_default_skippy__{workload}` | 1.0x | **论文 demo 关键数字**：fixed_node / default_skippy 比值 |
| `{policy}_vs_default_skippy__probe_avg_duration_relative__{workload}` | 0.0 | 相对 baseline 的相对变化 |

**关键诚实性事实**：跟 14 一致——`avg_probe_duration` 在两种 policy 下几乎一致（~0.22s），
`speedup_ratio = 1.0`，`relative change = 0.0`。sim 模型的 t_exec 等于 base_duration，
节点 capacity 不会改变 single-invoke duration。

## 5. 4 张图说明

### fig01 — Per-run probe_avg_duration
- 散点图：x = run_id，y = probe_avg_duration
- 颜色按 policy（绿=default_skippy，红=fixed_node），形状按 workload
- **论文价值**：跟 14 的 fig02 几乎一样（同样的 8 个 run 同样数据），但强调**"经过 15 聚合**"得到。

### fig02 — Policy comparison per workload（论文 demo 关键图）
- 柱状图：x = workload (low/medium)，y = mean_probe_avg_duration
- 每个 workload 两条柱：default_skippy (绿) vs fixed_node (红)
- 数字标注每条柱
- **论文价值**：视觉证明"两个 workload 下两种 policy 表现一致"——sim 模型的诚实性。

### fig03 — Policy high_capacity_node hit ratio
- 柱状图：default_skippy = 1.00, fixed_node = 0.00
- **论文价值**：跟 14 的 fig01 一样的核心数字（异构 capacity 拓扑下策略选择差异）。

### fig04 — Paper Highlight Metrics
- 双子图横向条形图：左侧是 count 指标，右侧是 policy/comparison 指标
- **论文价值**：避免 `total_probes=144` 和 `total_invocations=144` 把 0~1 的命中率、speedup、relative change 压扁，同时保留所有 demo 数字。

## 6. 与 02-14 的 demo 价值对比

| 维度 | 02 LB | 11 fault | 12 cold | 13 image | 14 batch | **15 analysis** |
|------|-------|---------|---------|----------|----------|-----------------|
| 验证目标 | 路由均衡 | 故障判定 | 冷启动路径 | 镜像缓存 | 批量实验框架 | **批量结果聚合** |
| 输入 | 仿真生成 | 仿真生成 | 仿真生成 | 仿真生成 | 仿真生成 | **14 的 outputs/** |
| 输出 | 1 份 csv | 1 份 csv | 1 份 csv | 2 场景 | 8 case 目录 | **5 份 csv + 1 份 md** |
| 探针 | dispatch | dispatch | dispatch | dispatch | dispatch+batch | **读 14 的 batch_invoke_probe** |
| 关键 join | route×probe | probe×fault | probe×inv | probe×flow | probe×inv (per case) | **summary vs paper_highlight** |
| 核心数字 | balance_std=0 | failure_rate=0.23 | first/warm=3.75x | cache=2.0x | hit_ratio=1.0/0.0 | **11/11 self_check PASS** |
| 论文 chart | 阶梯图 | 窗口散点 | Gantt | 双柱+散点 | 柱+散点+条 | **散点+双柱+柱+条** |

**15 的独特价值**：15 是 02-14 中**唯一一个"消费其他样例的输出"的样例**。
其他样例都是"端到端跑一个仿真 → 写论文"，15 是"读 14 的 CSV → 汇总 → 二次分析 → 写论文"。
15 还能扩展到读其他样例（02/05/06/08/11/12/13）的输出，做**跨样例的策略比较**。

## 7. 输出文件清单

```
examples/15_experiment_analysis/
├── main.py                                # 入口：loaders → metrics → aggregation → self_check → report
├── config.py                              # 输入/输出目录解析
├── loaders.py                             # 自动发现 run 目录 + 安全读 CSV
├── metrics.py                             # 单 run → 单行指标
├── aggregation.py                         # 聚合 + 策略对比 + paper_highlight
├── self_check.py                          # 11 项数据自检 + self_check.csv 输出
├── report.py                              # Markdown 报告生成
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── outputs/
│   ├── experiment_run_metrics.csv         # 每 case 单行
│   ├── experiment_summary.csv             # 按 (policy, workload) 聚合
│   ├── experiment_policy_comparison.csv   # 其他 policy vs default_skippy baseline
│   ├── experiment_paper_highlight.csv     # 论文 demo 关键摘要（19 metric + note）
│   ├── experiment_analysis_report.md      # Markdown 分析报告
│   └── self_check.csv                     # 11 项数据自检
└── figures/
    ├── fig01_per_run_probe_avg_duration.png/pdf
    ├── fig02_policy_comparison_per_workload.png/pdf
    ├── fig03_policy_high_capacity_hit_ratio.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **跨表一致性 self_check**：15 多了"summary vs paper_highlight 一致性"检查（4 个 cell），
  这是聚合分析样例的核心——保证 paper highlight 里的数字跟聚合摘要的源数据完全一致，
  避免论文里"两个表对不上"的低级错误。
- **强检查但保持简洁**：15 不只检查文件能生成，还强检查 total_probes == total_invocations、
  每个 run 的 probe_events == invocation_events、default_skippy == 1.0、fixed_node == 0.0。
  同时保留 4 个 summary vs highlight 一致性检查，这是聚合分析特有的检查。
- **Markdown 报告而非 HTML/JSON**：15 输出 Markdown 报告（6 节：输入信息 / Run-level 预览 /
  聚合摘要 / 策略对比 / 论文 demo / 说明），方便论文写作时直接 copy-paste 章节。
  没用 HTML/JSON 是为了最小化外部依赖（只需要 tabulate，没装就 fallback CSV 文本块）。
- **支持两种 run 目录结构**：`loaders.discover_run_dirs` 同时支持 `runs/<case_id>/`
  （14 的输出结构）和扁平 `<case_id>/` 结构（自包含的 run 目录），让 15 能消费
  其他样例的输出。
- **sample_results fallback**：14 的 outputs 不存在时，15 退到本样例自带的 sample_results，
  保证 `main.py` 在没有先跑 14 的情况下也能执行（demo 友好性）。但 15 仍然**优先读 14**，
  因为那才是"真实论文 demo 数据"的来源。
- **policy_comparison baseline 自身被跳过**：`build_policy_comparison` 跳过 baseline_policy
  自身，避免生成 `delta=0, relative=0` 的无意义行；self_check 验证"comparison 行数 == (policies-1) × workloads"，
  把这种跳过逻辑变成可验证的不变量。
- **诚实承认 sim 模型限制**：15 跟 14 一样，paper_highlight 显式指出"capacity 不改 single-invoke duration"，
  `speedup_ratio = 1.0` 和 `relative_change = 0.0` 是不变量而非意外结果。
