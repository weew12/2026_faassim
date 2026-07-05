"""
文件作用：image_cache 样例使用的序列固定节点调度器。

镜像缓存是节点本地状态。为了稳定对比“同节点复用缓存”和“不同节点各自冷拉取”，
本样例按照副本调度顺序指定目标节点：
- same_node_cache_reuse：两个函数副本都调度到 server_0；
- different_node_cold_pull：第一个副本调度到 server_0，第二个副本调度到 server_1。
"""

import logging
from typing import List

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, SchedulingResult
from skippy.core.utils import normalize_image_name

from sim.core import Environment

logger = logging.getLogger(__name__)


class SequenceNodeScheduler:
    """
    序列固定节点调度器。

    业务职责：
    - 按调度调用次数依次选择 target_node_names 中的目标节点；
    - 如果目标节点不存在，则回退到第一个 server 开头的节点；
    - 调度时同步调用 cluster_context.place_pod_on_node()；
    - 计算 needed_images，便于 schedule 指标展示镜像是否需要拉取。
    """

    def __init__(self, cluster_context: ClusterContext, target_node_names: List[str]):
        """
        初始化调度器。

        参数：
        - cluster_context：Skippy 集群上下文；
        - target_node_names：按调度顺序指定的目标节点名称。
        """
        self.cluster_context = cluster_context
        self.target_node_names = list(target_node_names)
        self.cursor = 0

    @staticmethod
    def create_same_node(env: Environment):
        """
        创建同节点缓存复用场景调度器。
        """
        logger.info("creating SequenceNodeScheduler for same_node_cache_reuse")
        return SequenceNodeScheduler(env.cluster, ["server_0", "server_0"])

    @staticmethod
    def create_different_node(env: Environment):
        """
        创建不同节点冷拉取场景调度器。
        """
        logger.info("creating SequenceNodeScheduler for different_node_cold_pull")
        return SequenceNodeScheduler(env.cluster, ["server_0", "server_1"])

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待调度 Pod 选择目标节点。
        """
        nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("SequenceNodeScheduler cannot schedule because cluster has no nodes")

        target_name = self._next_target_name()
        selected = self._find_node(nodes, target_name)

        if selected is None:
            selected = self._fallback_node(nodes)

        needed_images = self._needed_images(pod, selected)

        self.cluster_context.place_pod_on_node(pod, selected)

        logger.info(
            "SequenceNodeScheduler selected node=%s for pod=%s target=%s needed_images=%s",
            selected.name,
            pod.name,
            target_name,
            needed_images,
        )

        return SchedulingResult(
            suggested_host=selected,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )

    def _next_target_name(self) -> str:
        """
        返回本次调度目标节点名称。
        """
        if self.cursor < len(self.target_node_names):
            target_name = self.target_node_names[self.cursor]
        else:
            target_name = self.target_node_names[-1]

        self.cursor += 1
        return target_name

    @staticmethod
    def _find_node(nodes, target_name: str):
        """
        查找目标节点。
        """
        for node in nodes:
            if node.name == target_name:
                return node
        return None

    @staticmethod
    def _fallback_node(nodes):
        """
        选择回退节点。
        """
        for node in nodes:
            if node.name.startswith("server"):
                return node
        return nodes[0]

    def _needed_images(self, pod: Pod, selected_node) -> List[str]:
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
