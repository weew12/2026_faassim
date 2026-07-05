"""
fault_model 样例包。

本包用于演示 faas-sim 中故障模型的基本建模方式，重点覆盖：
- 节点不可用窗口；
- 函数副本瞬时失败；
- 网络退化导致请求执行时间变长；
- 故障事件时间线记录；
- fault_model_probe、fault_timeline、invocations 等指标导出。

运行入口：
    python -u examples/fault_model/main.py
"""
