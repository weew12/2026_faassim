"""
文件作用：自定义函数模拟器示例，演示如何实现 FunctionSimulator 生命周期方法并接入 SimulatorFactory。
主要类：CustomSimulatorFactory、MyFunctionSimulator。
主要函数：main。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
"""

import logging

import examples.basic.main as basic
import sim.docker as docker
from sim.core import Environment
from sim.faas import FunctionSimulator, FunctionReplica, FunctionRequest, SimulatorFactory, FunctionContainer
from sim.faassim import Simulation

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


def main():
    """
    函数作用：处理 main 相关业务逻辑。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    logging.basicConfig(level=logging.INFO)

    # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())

    
    sim.create_simulator_factory = CustomSimulatorFactory

    
    sim.run()


class CustomSimulatorFactory(SimulatorFactory):

    """
    类作用：CustomSimulatorFactory 工厂类，负责根据函数或配置创建对应组件实例。
    继承关系：SimulatorFactory。
    核心方法：__init__、create。
    """
    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return MyFunctionSimulator()


class MyFunctionSimulator(FunctionSimulator):

    """
    类作用：MyFunctionSimulator 类，封装 my、function、simulator 相关状态和业务操作。
    继承关系：FunctionSimulator。
    核心方法：deploy、startup、setup、invoke、teardown。
    """
    def deploy(self, env: Environment, replica: FunctionReplica):
        # 业务说明：这里处理镜像或数据下载，相关耗时会进入仿真时间。
        """
        函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
        关键流程：
        - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟副本启动阶段耗时，通常对应容器启动或运行时初始化。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        logger.info('[simtime=%.2f] starting up function replica for function %s', env.now, replica.function.name)

        
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(10)  

    def setup(self, env: Environment, replica: FunctionReplica):
        
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        
        

        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 向资源状态登记占用，反映函数副本在节点上的运行负载。
        - 从资源状态移除占用，避免已结束阶段继续影响资源利用率。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        logger.info('[simtime=%.2f] invoking function %s on node %s', env.now, request, replica.node.name)

        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        # 资源占用：登记函数当前阶段占用的资源。
        env.resource_state.put_resource(replica, 'cpu', cpu_millis)
        node = replica.node

        node.current_requests.add(request)

        if replica.function.name == 'python-pi':
            if replica.node.name.startswith('rpi3'):  # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
                # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
                yield env.timeout(20)  
            else:
                # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
                yield env.timeout(2)  # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        elif replica.function.name == 'resnet50-inference':
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(0.5)  
        else:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(0)

        
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        env.resource_state.remove_resource(replica, 'cpu', cpu_millis)
        node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟函数副本关闭阶段，释放资源并完成生命周期收尾。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)


if __name__ == '__main__':
    main()
