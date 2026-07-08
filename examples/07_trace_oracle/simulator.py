"""
文件作用：trace_oracle 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段从 TraceRuntimeOracle 中读取执行时间样本，
并使用该样本作为本次函数调用的执行时间。
"""

import logging
from pathlib import Path

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
)

from oracle import TraceRuntimeOracle

logger = logging.getLogger(__name__)


class TraceOracleSimulatorFactory(SimulatorFactory):
    """
    trace_oracle 样例的函数模拟器工厂。

    每个工厂持有一个 TraceRuntimeOracle，所有函数调用共享同一份 trace。
    """

    def __init__(self, trace_path: Path):
        """
        初始化模拟器工厂。

        参数：
        - trace_path：函数执行时间 trace CSV 文件路径。
        """
        self.trace_path = Path(trace_path)
        self.oracle = TraceRuntimeOracle(self.trace_path)

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return TraceOracleFunctionSimulator(self.oracle)


class TraceOracleFunctionSimulator(FunctionSimulator):
    """
    使用 trace oracle 的函数生命周期模拟器。

    样例重点：
    - deploy 阶段仍调用 docker.pull()；
    - startup/setup 使用固定较小开销；
    - invoke 阶段从 trace 中读取 duration；
    - 将 trace 取样过程记录到 trace_oracle_sample 指标。
    """

    def __init__(self, oracle: TraceRuntimeOracle):
        """
        初始化函数模拟器。
        """
        self.oracle = oracle

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
        yield env.timeout(0.15)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        执行时间来自 trace oracle，而不是固定常数。
        同时向 metrics 写 invoke_dispatch_probe（仿 02/03/05/06 模式），
        便于后续做 probe×invocation join 验证。
        """
        function_name = replica.function.name
        sample = self.oracle.sample(function_name)

        logger.info(
            "[simtime=%.2f] invoke request=%s function=%s sample_id=%d duration=%.4f node=%s",
            env.now,
            request.request_id,
            function_name,
            sample.sample_id,
            sample.duration,
            replica.node.name,
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        node = replica.node

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        node.current_requests.add(request)

        # 派发 probe：simtime + replica_id 关键标识
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
                "trace_sample_id": int(sample.sample_id),
                "trace_duration": float(sample.duration),
            },
            function_name=function_name,
            node=replica.node.name,
        )

        env.metrics.log(
            "trace_oracle_sample",
            {
                "sample_id": sample.sample_id,
                "duration": sample.duration,
            },
            function_name=function_name,
            request_id=request.request_id,
            node_name=replica.node.name,
            replica_id=id(replica),
        )

        yield env.timeout(sample.duration)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
