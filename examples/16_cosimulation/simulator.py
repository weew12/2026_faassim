"""
文件作用：cosimulation 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段读取 CosimulationContext 中的外部状态，
并根据 runtime_factor 与 network_delay 调整函数执行时间。
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

from context import CosimulationContext

logger = logging.getLogger(__name__)


class CosimulationSimulatorFactory(SimulatorFactory):
    """
    协同仿真函数模拟器工厂。
    """

    def __init__(self, context: CosimulationContext):
        """
        初始化工厂。
        """
        self.context = context

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return CosimulationFunctionSimulator(self.context)


class CosimulationFunctionSimulator(FunctionSimulator):
    """
    协同仿真函数生命周期模拟器。

    执行时间计算：

    final_duration = base_duration * runtime_factor + network_delay

    其中 runtime_factor 和 network_delay 来自外部控制器写入的共享上下文。
    """

    def __init__(self, context: CosimulationContext):
        """
        初始化函数模拟器。
        """
        self.context = context
        self.base_duration = 0.18

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，包含镜像拉取。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        yield env.timeout(0.2)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        本函数读取外部状态，并记录 cosim_invoke_probe。

        关键探针（沿用 02-15 的 invoke_dispatch_probe 模式）：
        入口 simtime + replica_id + request_id + expected_t_exec（按 cosim
        算出的 final_duration 真实派发）一并写两条探针（dispatch_probe +
        cosim_invoke_probe），便于 probe×invocation join 自洽检查。
        """
        snapshot = self.context.snapshot()

        runtime_factor = float(snapshot["runtime_factor"])
        network_delay = float(snapshot["network_delay"])
        final_duration = self.base_duration * runtime_factor + network_delay

        # 派发探针（沿用 02-15 模式）：simtime + replica_id + request_id + expected_t_exec
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
                "request_id": request.request_id,
                "expected_t_exec": float(final_duration),
            },
            function_name=replica.function.name,
            node=replica.node.name,
            phase_name=snapshot["phase_name"],
            controller_action=snapshot["controller_action"],
        )

        logger.info(
            "[simtime=%.2f] cosim invoke request=%s phase=%s action=%s duration=%.4f",
            env.now,
            request.request_id,
            snapshot["phase_name"],
            snapshot["controller_action"],
            final_duration,
        )

        env.metrics.log(
            "cosim_invoke_probe",
            {
                # simtime 字段：让 probe 跟 invocations 的 t_start 能直接 join
                # （sim.metrics 默认用 wall-clock 记录 `time` 列，simtime 只能手动塞）
                "simtime": float(env.now),
                "base_duration": self.base_duration,
                "runtime_factor": runtime_factor,
                "network_delay": network_delay,
                "final_duration": final_duration,
            },
            phase_name=snapshot["phase_name"],
            controller_action=snapshot["controller_action"],
            function_name=replica.function.name,
            request_id=request.request_id,
            node_name=replica.node.name,
            replica_id=id(replica),
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.12
        replica.node.current_requests.add(request)
        env.resource_state.put_resource(replica, "cpu", cpu_millis)

        yield env.timeout(final_duration)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        replica.node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
