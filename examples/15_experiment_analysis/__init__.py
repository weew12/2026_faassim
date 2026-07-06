"""
experiment_analysis 样例包。

本包用于演示 faas-sim 实验结果分析流程，重点覆盖：
- 统一发现实验 run 目录；
- 读取 case_result.csv、invocations.csv、schedule.csv、flow.csv 等结果文件；
- 为每个 run 生成标准化指标；
- 按 policy / workload 聚合结果；
- 生成策略对比表和 Markdown 分析报告。

运行入口：
    python -u examples/15_experiment_analysis/main.py
"""
