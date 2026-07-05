"""
文件作用：自动伸缩样例的 FaaS 系统工厂。

该文件集中封装系统创建逻辑，避免 main.py 中混入过多底层对象构造代码。
当前样例使用 faas-sim 原生 DefaultFaasSystem，并开启基于平均请求数的伸缩逻辑。
"""

import logging

from sim.core import Environment
from sim.faas.system import DefaultFaasSystem

logger = logging.getLogger(__name__)


def create_autoscaling_faas_system(env: Environment) -> DefaultFaasSystem:
    """
    创建启用自动伸缩能力的 DefaultFaasSystem。

    参数：
    - env：faas-sim 运行时环境。

    返回：
    - DefaultFaasSystem：启用 scale_by_average_requests 的 FaaS 系统实例。

    说明：
    - scale_by_average_requests=True 表示系统会根据平均请求负载触发副本伸缩；
    - 具体伸缩边界和目标负载由 FunctionDeployment 中的 ScalingConfiguration 决定；
    - 该函数用于被 Simulation.create_faas_system 接口引用。
    """
    logger.info("creating autoscaling DefaultFaasSystem")
    return DefaultFaasSystem(env, scale_by_average_requests=True)
