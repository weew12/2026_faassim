"""
文件作用：fault_model 样例使用的固定节点调度器。

故障模型样例需要稳定复现“目标节点发生故障”的现象。
因此本样例将函数副本固定调度到同一个节点，便于观察节点故障窗口、
副本失败和网络退化对请求执行结果的影响。
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
    该调度器只用于构造可重复的故障实验场景。
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
        logger.info("creating FixedNodeScheduler for fault model sample")
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
