"""
文件作用：degradation 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段读取当前节点已有并发请求数，并根据退化模型放大执行时间。
通过这种方式，可以观察同一节点多请求并发时的性能退化现象。
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

from degradation_model import LinearNodeContentionDegradationModel

logger = logging.getLogger(__name__)


class DegradationSimulatorFactory(SimulatorFactory):
    """
    degradation 样例的函数模拟器工厂。
    """

    def __init__(self):
        """
        初始化模拟器工厂。
        """
        self.model = LinearNodeContentionDegradationModel(
            base_duration=0.4,
            alpha=0.35,
        )

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return DegradationFunctionSimulator(self.model)


class DegradationFunctionSimulator(FunctionSimulator):
    """
    性能退化函数生命周期模拟器。

    样例重点：
    - deploy 阶段保持普通镜像拉取；
    - startup/setup 使用较小固定开销；
    - invoke 阶段根据节点 current_requests 计算退化后的执行时间；
    - 记录 degradation_probe 指标。
    """

    def __init__(self, model: LinearNodeContentionDegradationModel):
        """
        初始化函数模拟器。
        """
        self.model = model

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
        yield env.timeout(0.2)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用，并根据节点并发请求数计算退化后的执行时间。

        注意：
        active_requests_before 在当前请求加入 node.current_requests 之前读取，
        表示该请求到达时节点上已有的并发负载。
        """
        node = replica.node
        active_requests_before = len(node.current_requests)
        sample = self.model.sample(active_requests_before)

        logger.info(
            "[simtime=%.2f] invoke request=%s function=%s node=%s active_before=%d factor=%.3f duration=%.3f",
            env.now,
            request.request_id,
            replica.function.name,
            node.name,
            sample.active_requests_before,
            sample.degradation_factor,
            sample.final_duration,
        )

        cpu_millis = node.capacity.cpu_millis * 0.25
        memory_bytes = 96 * 1024 * 1024

        env.metrics.log(
            "degradation_probe",
            {
                "base_duration": sample.base_duration,
                "active_requests_before": sample.active_requests_before,
                "degradation_factor": sample.degradation_factor,
                "final_duration": sample.final_duration,
            },
            function_name=replica.function.name,
            request_id=request.request_id,
            node_name=node.name,
            replica_id=id(replica),
        )

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        env.resource_state.put_resource(replica, "memory", memory_bytes)
        node.current_requests.add(request)

        yield env.timeout(sample.final_duration)

        node.current_requests.remove(request)
        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        env.resource_state.remove_resource(replica, "memory", memory_bytes)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
