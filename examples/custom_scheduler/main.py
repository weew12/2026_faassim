"""
自定义调度器示例。

本示例复用 ``examples.basic`` 的拓扑和 benchmark，但通过
``sim.create_scheduler = CustomScheduler.create`` 替换默认调度器。示例调度策略非常
简单：从当前集群节点列表中随机选择一个节点，并把待部署 Pod 放到该节点上。

重点是展示调度器接入点和 ``schedule(pod) -> SchedulingResult`` 接口，而不是提供
生产级调度策略。
"""

import logging
import random

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import SchedulingResult, Pod

import examples.basic.main as basic
from sim.core import Environment
from sim.faassim import Simulation

logger = logging.getLogger(__name__)


def main():
    """
    运行基础 benchmark，并使用自定义调度器替换默认调度逻辑。
    """
    logging.basicConfig(level=logging.DEBUG)

    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())
    # faas-sim 创建 FaaS 系统时会调用该工厂方法创建 scheduler。
    sim.create_scheduler = CustomScheduler.create
    sim.run()


class CustomScheduler:
    """
    随机节点调度器。

    只保存 ``ClusterContext``，在每次 ``schedule`` 调用时从上下文读取可用节点列表。
    后续如果要实现资源感知、缓存感知或标签约束，可以从这里扩展。
    """

    def __init__(self, cluster: ClusterContext):
        # ClusterContext 向调度器暴露节点、资源、镜像缓存等集群视图。
        self.cluster = cluster

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待部署 Pod 选择目标节点。

        返回的 ``SchedulingResult`` 包含：
        - suggested_host：被选中的目标节点。
        - feasible_nodes：本示例直接填入节点总数。
        - needed_images：本示例不显式计算镜像拉取列表，因此返回空列表。
        """
        nodes = self.cluster.list_nodes()
        node = random.choice(nodes)

        logger.info("selected node %s for pod %s from total of %d nodes", node.name, pod.name, len(nodes))

        return SchedulingResult(node, len(nodes), list())

    @staticmethod
    def create(env: Environment):
        """
        调度器工厂方法。

        ``Simulation`` 会传入当前仿真环境；自定义调度器通常从 ``env.cluster`` 获取
        集群上下文，再返回一个 scheduler 实例。
        """
        logger.info('creating CustomScheduler')

        return CustomScheduler(env.cluster)


if __name__ == '__main__':
    main()
