"""
文件作用：fault_model 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段调用 DeterministicFaultModel 进行故障判定：
- 硬故障：请求快速失败，并记录 fault_model_probe；
- 软故障：请求成功，但执行时间增加；
- 正常请求：按基础执行时间完成。
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

from fault_model import DeterministicFaultModel

logger = logging.getLogger(__name__)


class FaultModelSimulatorFactory(SimulatorFactory):
    """
    fault_model 样例的函数模拟器工厂。
    """

    def __init__(self, fault_model: DeterministicFaultModel):
        """
        初始化模拟器工厂。
        """
        self.fault_model = fault_model

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return FaultModelFunctionSimulator(self.fault_model)


class FaultModelFunctionSimulator(FunctionSimulator):
    """
    故障模型函数生命周期模拟器。
    """

    def __init__(self, fault_model: DeterministicFaultModel):
        """
        初始化函数模拟器。
        """
        self.fault_model = fault_model

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
        模拟一次函数调用，并进行故障判定。

        注意：
        默认 DefaultFaasSystem 会在 invoke 返回后继续记录 invocations。
        因此本样例使用 fault_model_probe 作为请求成败的主要判断来源。
        """
        node = replica.node
        decision = self.fault_model.decide(env.now, request.request_id, node.name)

        logger.info(
            "[simtime=%.2f] fault decision request=%s function=%s node=%s success=%s reason=%s duration=%.3f",
            env.now,
            request.request_id,
            replica.function.name,
            node.name,
            decision.success,
            decision.reason,
            decision.final_duration,
        )

        env.metrics.log(
            "fault_model_probe",
            {
                "success": decision.success,
                "base_duration": decision.base_duration,
                "extra_delay": decision.extra_delay,
                "final_duration": decision.final_duration,
                "failure_latency": decision.failure_latency,
            },
            function_name=replica.function.name,
            request_id=request.request_id,
            node_name=node.name,
            replica_id=id(replica),
            reason=decision.reason,
            active_fault=decision.active_fault,
        )

        if not decision.success:
            yield env.timeout(decision.failure_latency)
            return

        cpu_millis = node.capacity.cpu_millis * 0.15
        memory_bytes = 64 * 1024 * 1024

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        env.resource_state.put_resource(replica, "memory", memory_bytes)
        node.current_requests.add(request)

        yield env.timeout(decision.final_duration)

        node.current_requests.remove(request)
        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        env.resource_state.remove_resource(replica, "memory", memory_bytes)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
