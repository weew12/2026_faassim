"""
batch_experiment 样例包。

本包用于演示 faas-sim 中批量实验的基本组织方式，重点覆盖：
- 多策略、多负载、多随机种子组合生成；
- 单次仿真实验运行与指标导出；
- 每个 run 独立输出目录；
- 汇总 batch_results.csv；
- 生成按策略和负载聚合的 batch_summary.csv。

运行入口：
    python -u examples/batch_experiment/main.py
"""
