"""
cold_start 样例包。

本包用于演示 faas-sim 中函数冷启动生命周期拆分建模，重点覆盖：
- deploy / image pull 阶段；
- startup 阶段；
- setup 阶段；
- first invoke 与 warm invoke 的区别；
- 副本首次可用时间与冷启动路径摘要导出。

运行入口：
    python -u examples/12_cold_start/main.py
"""
