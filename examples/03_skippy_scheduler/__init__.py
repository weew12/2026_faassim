"""
skippy_scheduler 样例包。

本包用于演示 faas-sim 原生 Skippy 默认调度机制，重点覆盖：
- 资源过滤；
- 节点可行性判断；
- 节点打分与选择；
- SchedulingResult 中 suggested_host / feasible_nodes / needed_images 的含义；
- 调度过程指标导出。

运行入口：
    python -u examples/03_skippy_scheduler/main.py
"""
