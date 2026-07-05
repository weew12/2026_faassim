"""
examples_autoscaling 包。

本包用于演示 faas-sim 原生自动伸缩能力，重点覆盖：
- ScalingConfiguration 的 min/max/目标负载配置；
- DefaultFaasSystem 的自动伸缩闭环；
- 函数副本数量随负载变化的记录；
- scale、schedule、replica_deployment、invocations 等指标导出。

运行入口：
    python -u examples/examples_autoscaling/main.py
"""
