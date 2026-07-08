"""
自定义函数模拟器示例。

本示例复用 ``examples.basic`` 的拓扑和 benchmark，但替换函数执行模型：
``CustomSimulatorFactory`` 为每个函数容器创建 ``MyFunctionSimulator``，后者实现
FunctionSimulator 生命周期方法，用固定耗时和资源占用模拟函数部署、启动、调用和关闭。

重点是展示如何把自定义 FunctionSimulator 接入 faas-sim，而不是重新定义拓扑或负载。
"""

import logging

import examples.basic.main as basic
import sim.docker as docker
from sim.core import Environment
from sim.faas import FunctionSimulator, FunctionReplica, FunctionRequest, SimulatorFactory, FunctionContainer
from sim.faassim import Simulation

logger = logging.getLogger(__name__)


def main():
    """
    运行基础 benchmark，并使用自定义函数模拟器。
    """
    logging.basicConfig(level=logging.INFO)

    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())
    # 覆盖默认工厂：之后部署的每个 FunctionContainer 都会使用 MyFunctionSimulator。
    sim.create_simulator_factory = CustomSimulatorFactory

    sim.run()


class CustomSimulatorFactory(SimulatorFactory):
    """
    自定义函数模拟器工厂。

    faas-sim 部署副本时会调用 ``create``。本示例不区分具体函数或镜像，统一返回
    ``MyFunctionSimulator``，便于观察完整生命周期接口如何被平台调用。
    """

    def __init__(self) -> None:
        super().__init__()

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        为函数容器创建自定义模拟器实例。

        ``env`` 和 ``fn`` 保留用于匹配接口；实际项目中可以根据 ``fn.fn_image``
        选择不同模拟器或配置不同参数。
        """
        return MyFunctionSimulator()


class MyFunctionSimulator(FunctionSimulator):
    """
    示例函数生命周期模拟器。

    实现的生命周期：
    - deploy：拉取容器镜像。
    - startup：模拟副本启动耗时。
    - setup：模拟副本初始化。
    - invoke：模拟一次请求执行，并记录临时 CPU 占用。
    - teardown：模拟副本关闭。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        拉取副本所需的容器镜像。

        ``docker.pull`` 会根据镜像大小、节点位置和网络链路推进仿真时间，因此部署
        延迟会影响副本何时可用。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟容器启动或运行时初始化耗时。

        这里固定等待 10 个仿真时间单位，用来强调 startup 会计入副本可用前的时间。
        """
        logger.info('[simtime=%.2f] starting up function replica for function %s', env.now, replica.function.name)

        yield env.timeout(10)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟副本启动后的业务初始化。

        示例中不额外消耗时间；真实模型可在这里模拟模型加载、缓存预热或连接建立。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数请求执行。

        该方法展示三件事：
        - 通过 ``env.resource_state`` 登记请求期间的临时 CPU 占用。
        - 通过 ``replica.node.current_requests`` 标记节点正在处理的请求。
        - 按函数名和节点类型设置不同执行耗时。
        """
        logger.info('[simtime=%.2f] invoking function %s on node %s', env.now, request, replica.node.name)

        # 临时占用当前节点 10% CPU，用于资源利用率统计。
        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        env.resource_state.put_resource(replica, 'cpu', cpu_millis)
        node = replica.node

        node.current_requests.add(request)

        if replica.function.name == 'python-pi':
            if replica.node.name.startswith('rpi3'):
                # Raspberry Pi 节点更慢，python-pi 需要更长执行时间。
                yield env.timeout(20)
            else:
                yield env.timeout(2)
        elif replica.function.name == 'resnet50-inference':
            yield env.timeout(0.5)
        else:
            yield env.timeout(0)

        env.resource_state.remove_resource(replica, 'cpu', cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟副本关闭。

        示例中不额外消耗时间；真实模型可在这里释放常驻资源或模拟关闭延迟。
        """
        yield env.timeout(0)


if __name__ == '__main__':
    main()
