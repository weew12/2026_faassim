"""
trace_oracle 样例包。

本包用于演示 faas-sim 中 trace-driven / oracle-style 的函数执行时间建模方式，重点覆盖：
- 从 CSV trace 读取函数执行时间样本；
- 基于 trace 的执行时间 Oracle；
- 函数 invoke 阶段如何从 Oracle 取样；
- 不同函数使用不同执行时间轨迹；
- invocations、trace_oracle_sample、summary 等结果导出。

运行入口：
    python -u examples/trace_oracle/main.py
"""
