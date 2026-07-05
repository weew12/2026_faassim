"""
文件作用：负载均衡样例的 FaaS 系统工厂。

该文件负责创建 DefaultFaasSystem，并将默认负载均衡器替换为
InstrumentedRoundRobinLoadBalancer。这样既保留原生轮询语义，
又能输出每次请求路由决策。
"""

import logging

from sim.core import Environment
from sim.faas.system import DefaultFaasSystem

from load_balancer import InstrumentedRoundRobinLoadBalancer

logger = logging.getLogger(__name__)


def create_load_balancer_faas_system(env: Environment) -> DefaultFaasSystem:
    """
    创建用于负载均衡样例的 FaaS 系统。

    参数：
    - env：faas-sim 运行时环境。

    返回：
    - DefaultFaasSystem：替换了负载均衡器的 FaaS 系统实例。

    说明：
    - DefaultFaasSystem 默认使用 RoundRobinLoadBalancer；
    - 本样例将其替换为 InstrumentedRoundRobinLoadBalancer；
    - 替换后的策略仍是轮询，但会额外记录 load_balancer 指标。
    """
    logger.info("creating DefaultFaasSystem with instrumented load balancer")

    system = DefaultFaasSystem(env)
    system.load_balancer = InstrumentedRoundRobinLoadBalancer(env, system.replicas)

    return system
