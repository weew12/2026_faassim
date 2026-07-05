# experiment_analysis：faas-sim 实验结果分析样例

本样例用于演示如何统一读取 faas-sim 实验输出 CSV，并生成标准化 summary 指标。它适合接在 `examples/batch_experiment/` 后面使用，也可以独立运行自带的 `sample_results/`。

## 运行方式

将 `experiment_analysis/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/experiment_analysis/main.py
```

默认情况下，脚本会优先读取：

```text
examples/batch_experiment/outputs/
```

如果该目录不存在或没有 `runs/` 子目录，则自动回退到：

```text
examples/experiment_analysis/sample_results/
```

也可以手动指定输入输出目录：

```bash
python -u examples/experiment_analysis/main.py --input-dir examples/batch_experiment/outputs
```

```bash
python -u examples/experiment_analysis/main.py --output-dir examples/experiment_analysis/outputs
```

## 文件结构

```text
experiment_analysis/
├── outputs/
├── sample_results/
│   └── runs/
├── __init__.py
├── 包结构说明_CN.md
├── aggregation.py
├── config.py
├── loaders.py
├── main.py
├── metrics.py
├── README_CN.md
└── report.py
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
examples/experiment_analysis/outputs/
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

## 后续扩展

该样例属于通用扩展功能样例。后续可以在此基础上继续扩展：

1. 增加置信区间；
2. 增加显著性检验；
3. 增加自动绘图；
4. 增加异常 run 检测；
5. 对接论文实验结果表格生成。
