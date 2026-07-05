"""
文件作用：image_pull_network 样例使用的固定节点调度器。

为了稳定观察镜像缓存效果，本样例需要让多个函数副本尽量部署到同一个节点。
如果第二个函数使用同一镜像并且被调度到同一节点，docker.pull() 会命中节点镜像缓存，
从而不再产生新的镜像拉取网络流。
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
    - 从 Skippy 集群上下文读取节点；
    - 优先选择 server_0；
    - 如果不存在 server_0，则选择第一个 server 开头的节点；
    - 如果仍不存在，则选择节点列表中的第一个节点。

    说明：
    该调度器不是正式调度策略，只用于稳定复现实验场景。
    """

    def __init__(self, cluster: ClusterContext, preferred_node_name: str = "server_0"):
        """
        初始化固定节点调度器。

        参数：
        - cluster：Skippy 集群上下文；
        - preferred_node_name：优先选择的节点名称。
        """
        self.cluster = cluster
        self.preferred_node_name = preferred_node_name

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating FixedNodeScheduler for image pull network sample")
        return FixedNodeScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待调度 Pod 选择目标节点。

        参数：
        - pod：Skippy 的 Pod 抽象。

        返回：
        - SchedulingResult：包含目标节点、候选节点数量和待拉取镜像列表。
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
