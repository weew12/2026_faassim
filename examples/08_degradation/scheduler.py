"""
文件作用：degradation 样例使用的固定节点调度器。

性能退化现象需要稳定制造“同一节点上存在多个并发请求”的场景。
因此本样例使用 FixedNodeScheduler 将函数副本固定调度到同一节点，
便于观察共节点并发导致的执行时间变长。
"""

import logging

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, SchedulingResult

from sim.core import Environment

logger = logging.getLogger(__name__)


class FixedNodeScheduler:
    """
    固定节点调度器。

    业务职责：
    - 优先选择 server_0；
    - 如果不存在 server_0，则选择第一个 server 开头的节点；
    - 如果仍不存在，则选择节点列表中的第一个节点。

    说明：
    该调度器只用于构造可重复实验场景，不作为正式调度策略。
    """

    def __init__(self, cluster: ClusterContext, preferred_node_name: str = "server_0"):
        """
        初始化固定节点调度器。
        """
        self.cluster = cluster
        self.preferred_node_name = preferred_node_name

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating FixedNodeScheduler for degradation sample")
        return FixedNodeScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待调度 Pod 选择目标节点。
        """
        nodes = self.cluster.list_nodes()

        if not nodes:
            raise RuntimeError("FixedNodeScheduler cannot schedule because cluster has no nodes")

        selected = None

        for node in nodes:
            if node.name == self.preferred_node_name:
                selected = node
                break

        if selected is None:
            for node in nodes:
                if node.name.startswith("server"):
                    selected = node
                    break

        if selected is None:
            selected = nodes[0]

        logger.info(
            "FixedNodeScheduler selected node=%s for pod=%s from total_nodes=%d",
            selected.name,
            pod.name,
            len(nodes),
        )

        return SchedulingResult(selected, len(nodes), list())
