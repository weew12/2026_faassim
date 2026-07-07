# 15_experiment_analysis：faas-sim 实验结果分析样例

本样例用于演示如何统一读取 faas-sim 实验输出 CSV，并生成标准化 summary 指标、策略对比表、论文 demo 关键摘要和数据自洽段。它**接在 `examples/14_batch_experiment/` 后面使用**（`main.py` 优先读 14 的 outputs）。

## 运行方式

将 `15_experiment_analysis/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/15_experiment_analysis/main.py
```

默认情况下，脚本会优先读取：

```text
examples/14_batch_experiment/outputs/
```

也可以手动指定输入输出目录：

```bash
python -u examples/15_experiment_analysis/main.py --input-dir examples/14_batch_experiment/outputs
```

```bash
python -u examples/15_experiment_analysis/main.py --output-dir examples/15_experiment_analysis/outputs
```

## 样例目标

该样例主要回答以下问题：

1. 如何自动发现多个 run 目录（同时支持 `runs/<case_id>/` 结构和扁平 `<case_id>/` 结构）；
2. 如何统一读取 `case_result.csv`、`batch_invoke_probe.csv`、`invocations.csv`、`schedule.csv`、`flow.csv` 等文件（缺失文件安全跳过）；
3. 如何为每个 run 生成标准化指标（含 `scheduled_node` 提取供论文摘要用）；
4. 如何按 `policy` 和 `workload` 聚合结果；
5. 如何以 `default_skippy` 为基线生成策略对比表（baseline 自身被跳过）；
6. 如何生成论文 demo 关键摘要（`high_capacity_hit_ratio` + `speedup_ratio` + per-workload relative change）；
7. 如何做数据自洽段（9 个不变量）；
8. 如何生成 Markdown 分析报告。

## 输出文件

运行结束后，结果会保存到：

```text
examples/15_experiment_analysis/outputs/
```

主要文件：

```text
experiment_run_metrics.csv            # run-level 单行结果（每 case 一行）
experiment_summary.csv                # 按 (policy, workload) 聚合
experiment_policy_comparison.csv      # 其他 policy vs default_skippy baseline
experiment_paper_highlight.csv        # 论文 demo 关键摘要
experiment_analysis_report.md         # Markdown 分析报告
```

### 1. `experiment_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                                                value
scheduled_nodes__default_skippy                                       server_1
high_capacity_hit_ratio__default_skippy                               1.000
scheduled_nodes__fixed_node                                           server_0
high_capacity_hit_ratio__fixed_node                                   0.000
default_skippy__avg_probe_seconds__low_load                           0.221
fixed_node__avg_probe_seconds__low_load                               0.221
default_skippy__avg_probe_seconds__medium_load                        0.220
fixed_node__avg_probe_seconds__medium_load                            0.220
speedup_ratio_fixed_over_default_skippy__low_load                     1.000
speedup_ratio_fixed_over_default_skippy__medium_load                  1.000
fixed_node_vs_default_skippy__probe_avg_duration_relative__low_load  0.000
fixed_node_vs_default_skippy__probe_avg_duration_relative__medium_load 0.000
```

**关键发现**：
- `default_skippy` 100% 命中 capacity 最大的 server_1（8 cpu）。
- `fixed_node` 100% 选 server_0（1 cpu）。
- `avg_probe_seconds` 两边一致 —— 跟 14 的 paper highlight 保持一致。

### 2. `experiment_policy_comparison.csv` —— 其他 policy vs baseline

由于 `default_skippy` 是 baseline，`fixed_node` 是唯一非 baseline，所以只有 2 行（2 workloads）。

```text
workload    baseline_policy  policy        mean_probe_avg_duration_relative  ...
low_load    default_skippy   fixed_node    0.000
medium_load default_skippy   fixed_node    0.000
```

### 3. `experiment_analysis_report.md` —— Markdown 报告

包含 6 节：输入信息、Run-level 预览、聚合摘要、策略对比、论文 demo 关键摘要、说明。

## 数据自洽验证

跑完 `main.py` 后，**9 个核心不变量**应同时满足（9/9 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1 | `run_metrics` 行数 >= 2 | self-check |
| 2 | `summary` 行数 = policies × workloads（2×2=4） | self-check |
| 3 | `comparison` 行数 = (policies-1) × workloads（1×2=2，baseline 跳过） | self-check |
| 4 | paper highlight 的 `high_capacity_hit_ratio__default_skippy == 1.0` | self-check |
| 5 | paper highlight 的 `high_capacity_hit_ratio__fixed_node == 0.0` | self-check |
| 6-9 | paper highlight 的 `avg_probe_seconds__<workload>` 跟 summary 完全一致（4 个 cell） | self-check |

自洽段 log 在 main 末尾：

```text
INFO:self_check:=== experiment_analysis self-check ===
INFO:self_check:  [PASS] run_metrics_min_rows : run_metrics rows=8
INFO:self_check:  [PASS] summary_row_count : summary rows=4, expected=4 (policies=2 × workloads=2)
INFO:self_check:  [PASS] comparison_row_count : comparison rows=2, expected=2 ((policies-1=1) × workloads=2)
INFO:self_check:  [PASS] high_capacity_hit_ratio__default_skippy : hit 4/4 = 1.00, highlight=1.00
INFO:self_check:  [PASS] high_capacity_hit_ratio__fixed_node : hit 0/4 = 0.00, highlight=0.00
INFO:self_check:  [PASS] avg_probe_seconds_consistency__default_skippy__low_load : summary=0.221079, highlight=0.221079
INFO:self_check:  [PASS] avg_probe_seconds_consistency__default_skippy__medium_load : summary=0.219739, highlight=0.219739
INFO:self_check:  [PASS] avg_probe_seconds_consistency__fixed_node__low_load : summary=0.221079, highlight=0.221079
INFO:self_check:  [PASS] avg_probe_seconds_consistency__fixed_node__medium_load : summary=0.219739, highlight=0.219739
INFO:self_check:=== 9 passed, 0 failed ===
```

## 与 batch_experiment 的关系

`batch_experiment` 负责运行多组仿真实验并产生原始 CSV；`experiment_analysis` 负责读取这些 CSV 并生成统计摘要 + 论文 demo 关键摘要 + 数据自洽段。两者组合后形成一个**最小实验自动化闭环**：

```text
batch_experiment 运行实验 → outputs/runs/<case_id>/*.csv
                          ↓
experiment_analysis 汇总结果 → experiment_run_metrics.csv
                            → experiment_summary.csv
                            → experiment_policy_comparison.csv
                            → experiment_paper_highlight.csv
                            → experiment_analysis_report.md
                            + 数据自洽段（9 个不变量）
```

## 目录结构

```text
15_experiment_analysis/
├── outputs/                              # 运行输出（5 个 csv + 1 个 md）
├── __init__.py
├── aggregation.py                        # 聚合 + 策略对比 + paper highlight
├── config.py                             # 默认输入路径（14_batch_experiment/outputs/）
├── loaders.py                            # 通用 CSV 加载器
├── main.py                               # 入口（含 self-check 段）
├── metrics.py                            # run-level 单行指标
├── report.py                             # Markdown 报告生成
└── self_check.py                         # 9 个不变量自洽段
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 解析命令行参数（`--input-dir` / `--output-dir`）；
2. 定位输入目录（默认 14 的 outputs）；
3. 读取所有 run；
4. 构建 run-level 指标 + summary + comparison + paper highlight；
5. 生成 Markdown 报告；
6. 跑数据自洽段（9 个不变量）；
7. log paper highlight（高 capacity 命中率）。

### `config.py`

分析配置文件。

集中定义输入目录、输出目录、来源名称（`batch_experiment_outputs` 或 `sample_results`）。

### `loaders.py`

CSV 加载文件。

- `discover_run_dirs`：同时支持 `input_dir/runs/<case_id>` 结构和扁平 `input_dir/<case_id>` 结构。
- `read_csv_safe`：文件不存在或读取失败时返回空 DataFrame，保证分析流程不中断。

### `metrics.py`

单次实验指标计算文件。

- 从 `case_result.csv` 取 `case_id` / `policy` / `workload` / `seed` / `rps` / `max_requests` / **`scheduled_node`**（14 已预聚合）。
- 从 `batch_invoke_probe.csv` 算 `probe_avg_duration` / `probe_p95_duration`。
- 从 `invocations.csv` 算 `invocation_avg_duration`。
- 从 `schedule.csv` 算 `scheduled_node_count` / `scheduled_nodes`。
- 从 `flow.csv` 算 `flow_total_bytes` / `flow_total_duration`。
- 从 `replica_deployment.csv` 算 `replica_deployment_events`。

### `aggregation.py`

批量聚合 + 策略对比 + 论文 demo 关键摘要文件。

- `aggregate_by_policy_workload`：按 policy × workload 分组聚合。
- `build_policy_comparison`：以 `default_skippy` 为 baseline 计算相对变化（baseline 自身被跳过）。
- `build_paper_highlight`：与 14 的 `batch_paper_highlight` 风格一致 —— 包含 `scheduled_nodes` / `high_capacity_hit_ratio` / `avg_probe_seconds__<workload>` / `speedup_ratio` / per-workload relative change。

### `report.py`

报告生成文件。

6 节 Markdown 报告：输入信息、Run-level 预览、聚合摘要、策略对比、论文 demo 关键摘要、说明。

### `self_check.py`

数据自洽段文件。

9 个不变量：run_metrics 行数、summary 行数、comparison 行数、2 个 high_capacity_hit_ratio、4 个 avg_probe_seconds_consistency。

### `outputs/`

分析结果输出目录。

包含 4 个 CSV + 1 个 Markdown 报告。
