"""
文件作用：Skippy 调度样例使用的函数执行模拟器。

该模拟器主要用于让函数副本完成 deploy/startup/setup/invoke 生命周期，
从而让调度、部署和调用指标都能正常产生。
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


class SkippySchedulerSimulatorFactory(SimulatorFactory):
    """
    Skippy 调度样例的函数模拟器工厂。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return SkippySchedulerFunctionSimulator()


class SkippySchedulerFunctionSimulator(FunctionSimulator):
    """
    Skippy 调度实验使用的函数生命周期模拟器。

    当前执行时间固定为 0.25 个仿真时间单位，便于快速完成样例。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段。

        这里调用 docker.pull，用于触发镜像拉取和 needed_images 相关逻辑。
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

        在 invoke 开始时写 invoke_dispatch_probe（simtime + replica_id），
        后续 analysis.py 用 probe×invocation join 验证：
        每个 invoke 派发事件都能从 invocations.csv 找到匹配的
        (function, replica, simtime) 调用记录。
        """
        # 派发 probe：simtime + replica_id 关键标识，方便后续 join
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
            },
            function_name=replica.function.name,
            node=replica.node.name,
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        node = replica.node

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        node.current_requests.add(request)

        yield env.timeout(0.25)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
