"""
文件作用：自定义调度器示例，演示如何替换默认调度逻辑并将副本放置到指定节点。
主要类：CustomScheduler。
主要函数：main。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
"""

import logging
import random

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import SchedulingResult, Pod

import examples.basic.main as basic
from sim.core import Environment
from sim.faassim import Simulation

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


def main():
    """
    函数作用：处理 main 相关业务逻辑。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    logging.basicConfig(level=logging.DEBUG)

    # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())

    # 业务说明：这里与副本放置或调度决策有关。
    sim.create_scheduler = CustomScheduler.create

    
    sim.run()


class CustomScheduler:
    """
    类作用：CustomScheduler 类，封装 custom、scheduler 相关状态和业务操作。
    核心方法：__init__、schedule、create。
    """

    def __init__(self, cluster: ClusterContext):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：cluster。
        参数：cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。
        self.cluster = cluster

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        函数作用：为待部署副本选择目标节点并返回调度结果。
        关键流程：
        - 使用随机采样生成设备属性、请求间隔或性能取值。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：pod：调度器使用的 Pod 视图。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """

        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        nodes = self.cluster.list_nodes()

        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        node = random.choice(nodes)

        logger.info("selected node %s for pod %s from total of %d nodes", node.name, pod.name, len(nodes))

        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        return SchedulingResult(node, len(nodes), list())

    @staticmethod
    def create(env: Environment):
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        logger.info('creating CustomScheduler')
        
        return CustomScheduler(env.cluster)


if __name__ == '__main__':
    main()
