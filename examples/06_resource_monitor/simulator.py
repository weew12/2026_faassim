"""
文件作用：resource_monitor 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段显式登记 CPU / memory 资源占用，并保持一段执行时间，
从而让 faas-sim 的 ResourceMonitor 能采集到资源使用变化。
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


class ResourceMonitorSimulatorFactory(SimulatorFactory):
    """
    resource_monitor 样例的函数模拟器工厂。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return ResourceMonitorFunctionSimulator()


class ResourceMonitorFunctionSimulator(FunctionSimulator):
    """
    资源监控实验使用的函数生命周期模拟器。

    样例重点：
    - deploy 阶段仍调用 docker.pull()，保持和普通函数部署一致；
    - invoke 阶段登记 CPU / memory；
    - 执行结束后释放 CPU / memory；
    - ResourceMonitor 会周期性读取 ResourceState 并记录指标。
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
        yield env.timeout(0.2)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用，并显式登记资源占用。

        资源占用设计：
        - CPU 占用设置为节点 CPU 容量的 35%；
        - 内存占用设置为 128 MiB；
        - 执行时间保持 1.5 个仿真时间单位；
        - 执行结束后释放资源。

        同时向 metrics 写 invoke_dispatch_probe（仿 02/03/05 模式），
        便于后续做 probe×invocation join 验证。

        这样 ResourceMonitor 在请求执行期间能够采集到明显的资源变化。
        """
        node = replica.node

        cpu_millis = node.capacity.cpu_millis * 0.35
        memory_bytes = 128 * 1024 * 1024

        # 派发 probe：simtime + replica_id 关键标识
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
                "cpu_millis": float(cpu_millis),
                "memory_bytes": float(memory_bytes),
            },
            function_name=replica.function.name,
            node=replica.node.name,
        )

        logger.info(
            "[simtime=%.2f] invoke request=%s function=%s node=%s cpu=%.2f memory=%d",
            env.now,
            request.request_id,
            replica.function.name,
            node.name,
            cpu_millis,
            memory_bytes,
        )

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        env.resource_state.put_resource(replica, "memory", memory_bytes)
        node.current_requests.add(request)

        yield env.timeout(1.5)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        env.resource_state.remove_resource(replica, "memory", memory_bytes)
        node.current_requests.remove(request)

        logger.info(
            "[simtime=%.2f] finish request=%s function=%s node=%s",
            env.now,
            request.request_id,
            replica.function.name,
            node.name,
        )

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
