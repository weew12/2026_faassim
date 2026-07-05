# experiment_analysis 包结构说明

`experiment_analysis` 是 faas-sim 实验结果分析样例包，用于统一读取多个 run 的 CSV 结果并生成 summary 指标。

## 目录结构

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

该文件负责解析默认输入路径。脚本会优先读取 `examples/batch_experiment/outputs/`，如果不存在则使用 `sample_results/`。

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

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/experiment_analysis/main.py
```

## 样例定位

该样例属于“通用扩展功能样例”。

它用于把单次或批量仿真结果转化为可读的 summary 指标，为后续论文实验统计、表格生成和自动绘图提供基础。
