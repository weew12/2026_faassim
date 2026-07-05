"""
examples_load_balancer 包。

本包用于演示 faas-sim 原生负载均衡能力，重点覆盖：
- 多函数副本部署；
- DefaultFaasSystem 中负载均衡器的替换方式；
- 请求如何被分配到不同 FunctionReplica；
- load_balancer、invocations、schedule、replica_deployment 等指标导出。

运行入口：
    python -u examples/examples_load_balancer/main.py
"""
