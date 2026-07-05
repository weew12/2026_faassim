"""
文件作用：负载均衡样例使用的函数执行模拟器。

该模拟器用于给函数请求提供稳定执行时间和简单资源占用。
在多副本场景下，它可以帮助观察请求是否被负载均衡器分散到不同副本。
"""

import logging

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
)

logger = logging.getLogger(__name__)


class LoadBalancerSimulatorFactory(SimulatorFactory):
    """
    负载均衡样例的函数模拟器工厂。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return LoadBalancerFunctionSimulator()


class LoadBalancerFunctionSimulator(FunctionSimulator):
    """
    负载均衡实验使用的函数生命周期模拟器。

    当前执行时间固定为 0.3 个仿真时间单位。
    该值足够短，便于快速完成样例；同时不为 0，便于观察请求执行过程。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，包含镜像拉取。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        logger.info(
            "[simtime=%.2f] startup replica for function %s on node %s",
            env.now,
            replica.function.name,
            replica.node.name,
        )
        yield env.timeout(0.3)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        执行期间登记 CPU 占用，并维护 node.current_requests。
        """
        logger.debug(
            "[simtime=%.2f] invoke request=%s function=%s node=%s replica_id=%s",
            env.now,
            request,
            replica.function.name,
            replica.node.name,
            id(replica),
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        node = replica.node

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        node.current_requests.add(request)

        yield env.timeout(0.3)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
