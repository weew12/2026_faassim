"""
degradation 样例包。

本包用于演示 faas-sim 中性能退化建模的基本思路，重点覆盖：
- 多个请求在同一节点并发执行时的资源竞争；
- 节点 current_requests 如何反映当前并发负载；
- 函数执行时间如何随并发请求数增加而变长；
- degradation_probe、invocations、replica_deployment 等指标导出。

运行入口：
    python -u examples/degradation/main.py
"""
