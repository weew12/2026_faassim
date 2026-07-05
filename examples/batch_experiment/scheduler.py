"""
文件作用：batch_experiment 样例使用的辅助调度器。

默认策略使用 faas-sim / Skippy 原生调度器，不需要自定义代码。
fixed_node 策略使用 FixedNodeScheduler，用于展示批量实验中如何切换策略。
"""

import logging
from typing import Optional

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, SchedulingResult
from skippy.core.utils import normalize_image_name

from sim.core import Environment

logger = logging.getLogger(__name__)


class FixedNodeScheduler:
    """
    固定节点调度器。

    该策略用于批量实验中的对照组，固定把函数副本放到同一个节点。
    """

    def __init__(self, cluster_context: ClusterContext, preferred_node_name: str = "server_0"):
        """
        初始化调度器。
        """
        self.cluster_context = cluster_context
        self.preferred_node_name = preferred_node_name

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating FixedNodeScheduler for batch experiment")
        return FixedNodeScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待调度 Pod 选择目标节点。
        """
        nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("FixedNodeScheduler cannot schedule because cluster has no nodes")

        selected = self._find_node(nodes, self.preferred_node_name)

        if selected is None:
            selected = self._fallback_node(nodes)

        needed_images = self._needed_images(pod, selected)

        self.cluster_context.place_pod_on_node(pod, selected)

        logger.info(
            "FixedNodeScheduler selected node=%s for pod=%s needed_images=%s",
            selected.name,
            pod.name,
            needed_images,
        )

        return SchedulingResult(
            suggested_host=selected,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )

    @staticmethod
    def _find_node(nodes, target_name: str) -> Optional[Node]:
        """
        查找目标节点。
        """
        for node in nodes:
            if node.name == target_name:
                return node
        return None

    @staticmethod
    def _fallback_node(nodes) -> Node:
        """
        选择回退节点。
        """
        for node in nodes:
            if node.name.startswith("server"):
                return node
        return nodes[0]

    def _needed_images(self, pod: Pod, selected_node: Node):
        """
        计算目标节点上尚未存在的镜像。
        """
        needed_images = []
        host_images = self.cluster_context.images_on_nodes[selected_node.name]

        for container in pod.spec.containers:
            image_name = normalize_image_name(container.image)
            if image_name not in host_images:
                needed_images.append(image_name)

        return needed_images
