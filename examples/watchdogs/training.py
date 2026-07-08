"""
训练函数模拟器示例。

TrainingFunctionSim 继承 ForkingWatchdog，用来模拟偏长耗时、偏高资源占用的
训练任务。Forking 模式下每个请求都会直接进入 claim -> execute -> release
流程，不经过 HTTP worker 队列。
"""

import logging

from sim import docker
from sim.core import Environment
from sim.faas import ForkingWatchdog, FunctionReplica, FunctionRequest

logger = logging.getLogger(__name__)


class TrainingFunctionSim(ForkingWatchdog):
    """
    ResNet 训练函数的 forking watchdog 实现。

    训练请求在本示例中被拆成启动、资源声明、三段执行耗时和资源释放。与
    HTTPWatchdog 不同，ForkingWatchdog 不限制副本内部 worker 数；如需限制训练
    并发，应在上层调度、伸缩或请求生成逻辑中控制。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        拉取训练镜像。

        镜像大小由 benchmark setup 中注册的 ImageProperties 决定，拉取耗时会进入
        SimPy 仿真时间。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟训练副本启动耗时。

        这里用 1 个仿真时间单位近似容器启动、运行时初始化或训练框架加载。
        """
        logger.info('[simtime=%.2f] starting up function replica for function %s', env.now, replica.function.name)

        yield env.timeout(1)

    def claim_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        为一次训练请求登记执行期资源占用。

        CPU 和 memory 数值是示例参数，用于让资源监控和调度指标能看到训练请求对
        节点造成的负载。
        """
        env.resource_state.put_resource(replica, 'cpu', 0.7)
        env.resource_state.put_resource(replica, 'memory', 0.3)
        yield env.timeout(0)

    def release_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        释放一次训练请求的执行期资源占用。
        """
        env.resource_state.remove_resource(replica, 'cpu', 0.2)
        yield env.timeout(0)

    def execute(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟训练任务主体。

        三段 timeout 分别近似数据准备、训练计算和结果写回。拆成多段后，后续如果要
        插入指标、网络传输或故障注入，会比单个长 timeout 更容易扩展。
        """
        # 数据准备阶段。
        yield env.timeout(1)

        # 主训练计算阶段。
        yield env.timeout(5)

        # 结果写回或收尾阶段。
        yield env.timeout(1)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        关闭训练副本。

        本示例不额外建模关闭成本，仅保留协程接口以匹配 FunctionSimulator 生命周期。
        """
        yield env.timeout(0)
