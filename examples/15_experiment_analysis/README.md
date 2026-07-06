# 15_experiment_analysis：faas-sim 实验结果分析样例

本样例用于演示如何统一读取 faas-sim 实验输出 CSV，并生成标准化 summary 指标。它适合接在 `examples/14_batch_experiment/` 后面使用，也可以独立运行自带的 `sample_results/`。

## 运行方式

将 `experiment_analysis/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/15_experiment_analysis/main.py
```

默认情况下，脚本会优先读取：

```text
examples/14_batch_experiment/outputs/
```

如果该目录不存在或没有 `runs/` 子目录，则自动回退到：

```text
examples/15_experiment_analysis/sample_results/
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

1. 如何自动发现多个 run 目录；
2. 如何统一读取 `case_result.csv`、`invocations.csv`、`schedule.csv`、`flow.csv` 等文件；
3. 如何为每个 run 生成标准化指标；
4. 如何按 `policy` 和 `workload` 聚合结果；
5. 如何以 `default_skippy` 为基线生成策略对比表；
6. 如何生成 Markdown 分析报告。

## 输出文件

运行结束后，结果会保存到：

```text
examples/15_experiment_analysis/outputs/
```

主要包括：

```text
experiment_run_metrics.csv
experiment_summary.csv
experiment_policy_comparison.csv
experiment_analysis_report.md
```

## 与 batch_experiment 的关系

`batch_experiment` 负责运行多组仿真实验并产生原始 CSV；`experiment_analysis` 负责读取这些 CSV 并生成统计摘要。两者组合后，可以形成一个最小的实验自动化闭环：

```text
batch_experiment 运行实验
experiment_analysis 汇总结果
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 解析命令行参数；
2. 定位输入目录；
3. 读取所有 run；
4. 构建 run-level 指标；
5. 聚合 policy / workload 摘要；
6. 生成策略对比和 Markdown 报告。

### `config.py`

分析配置文件。

该文件负责解析默认输入路径。脚本会优先读取 `examples/14_batch_experiment/outputs/`，如果不存在则使用 `sample_results/`。

### `loaders.py`

CSV 加载文件。

该文件负责发现 run 目录，并读取常见 CSV 文件。缺失文件会被安全跳过。

### `metrics.py`

单次实验指标计算文件。

该文件把单个 run 的多张 CSV 表压缩成一行标准化结果。

### `aggregation.py`

批量聚合文件。

该文件负责按 `policy` 和 `workload` 聚合结果，并生成策略对比表。

### `report.py`

报告生成文件。

该文件负责生成 `experiment_analysis_report.md`。

### `sample_results/`

内置样例数据目录。

当没有先运行 `batch_experiment` 时，可以使用该目录验证分析脚本是否正常工作。

### `outputs/`

分析结果输出目录。

用于保存：

```text
experiment_run_metrics.csv
experiment_summary.csv
experiment_policy_comparison.csv
experiment_analysis_report.md
```