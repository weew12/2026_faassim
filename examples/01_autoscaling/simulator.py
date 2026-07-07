"""
文件作用：自动伸缩样例使用的函数执行模拟器。

该模拟器用于给函数请求提供稳定、可控的执行时间和资源占用。
这样在不同请求负载下，可以观察自动伸缩逻辑如何改变函数副本数量。
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


class AutoscalingSimulatorFactory(SimulatorFactory):
    """
    自动伸缩样例的函数模拟器工厂。

    faas-sim 在创建函数副本时会调用 create 方法，为该副本绑定一个 FunctionSimulator。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数执行模拟器。

        参数：
        - env：faas-sim 运行时环境；
        - fn：函数容器配置。

        返回：
        - AutoscalingFunctionSimulator：本样例使用的函数生命周期模拟器。
        """
        return AutoscalingFunctionSimulator()


class AutoscalingFunctionSimulator(FunctionSimulator):
    """
    自动伸缩实验使用的函数生命周期模拟器。

    该模拟器将函数执行时间固定为 0.2 个仿真时间单位，
    并在执行期间登记 CPU 资源占用，便于后续资源监控样例继续复用。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段。

        当前阶段会触发 docker.pull，用于模拟镜像拉取。
        如果目标节点已经缓存镜像，拉取耗时会降低或跳过。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。

        启动阶段设置为 0.5 个仿真时间单位，避免启动过慢掩盖自动伸缩行为。
        """
        logger.info(
            "[simtime=%.2f] startup replica for function %s on node %s",
            env.now,
            replica.function.name,
            replica.node.name,
        )
        yield env.timeout(0.5)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。

        当前样例不额外模拟模型加载或缓存预热，因此耗时为 0。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        业务流程：
        1. 记录 autoscaling_invoke_probe（含 simtime 字段，用于跟 invocations.csv 关联）；
        2. 登记 CPU 占用；
        3. 将请求加入节点当前请求集合；
        4. 等待固定执行时间；
        5. 释放 CPU 占用；
        6. 从节点当前请求集合移除请求。
        """
        logger.debug(
            "[simtime=%.2f] invoke request=%s function=%s node=%s",
            env.now,
            request,
            replica.function.name,
            replica.node.name,
        )

        # 记录 invoke probe（论文 demo 关键证据：simulator 派发的 t_exec 跟 invocations.csv 的 t_exec 关联）
        env.metrics.log(
            "autoscaling_invoke_probe",
            {
                # simtime 字段：让 probe 跟 invocations 的 t_start 能直接 join
                "simtime": float(env.now),
                "t_exec": 0.2,
            },
            function_name=replica.function.name,
            request_id=request.request_id,
            node_name=replica.node.name,
            replica_id=id(replica),
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.15
        node = replica.node

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        node.current_requests.add(request)

        yield env.timeout(0.2)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。

        当前样例不额外模拟关闭耗时。
        """
        yield env.timeout(0)
