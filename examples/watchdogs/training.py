"""
文件作用：训练函数模拟器示例，模拟训练任务的启动、资源占用、执行和释放过程。
主要类：TrainingFunctionSim。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
"""

import logging

from sim import docker
from sim.core import Environment
from sim.faas import ForkingWatchdog, FunctionReplica, FunctionRequest

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


class TrainingFunctionSim(ForkingWatchdog):
    """
    类作用：TrainingFunctionSim 类，封装 training、function、sim 相关状态和业务操作。
    继承关系：ForkingWatchdog。
    核心方法：deploy、startup、claim_resources、release_resources、execute、teardown。
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
        yield env.timeout(1)  

    def claim_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：在资源状态中声明函数执行阶段需要占用的资源。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 向资源状态登记占用，反映函数副本在节点上的运行负载。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 资源占用：登记函数当前阶段占用的资源。
        env.resource_state.put_resource(replica, 'cpu', 0.7)
        # 资源占用：登记函数当前阶段占用的资源。
        env.resource_state.put_resource(replica, 'memory', 0.3)
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def release_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：释放函数执行阶段占用的资源。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 从资源状态移除占用，避免已结束阶段继续影响资源利用率。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        env.resource_state.remove_resource(replica, 'cpu', 0.2)
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def execute(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        # 业务说明：这里处理镜像或数据下载，相关耗时会进入仿真时间。
        """
        函数作用：模拟用户函数主体逻辑的执行耗时。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(1)

        
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(5)

        
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(1)

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
