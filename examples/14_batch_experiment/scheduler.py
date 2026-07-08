"""
文件作用：batch_experiment 样例使用的辅助调度器。

默认策略使用 Skippy 原生 default_skippy 调度器（但 faas-sim 的 Skippy 默认
    predicates 在我们的小拓扑里都把 server_0 当成第一个候选，导致 default_skippy
    实际上跟 fixed_node 都选 server_0，看不出策略差异）。

为了清晰展示策略对比，本样例额外提供：
- fixed_node 策略：FixedNodeScheduler，固定选 server_0
- default_skippy 策略：实际是 CapacityAwareScheduler，选 capacity 最大的节点
  （这样 default_skippy 选 server_1，fixed_node 选 server_0，节点选择产生差异）

如果你的 faas-sim Skippy 默认调度器在最小拓扑上确实能选到不同节点（按 Skippy 内部
priorities 排序），可以把 default_skippy 改回 faas-sim 原生调度器。
"""

import logging
from typing import List, Optional

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

        如果首选节点不在集群中，直接抛异常（不再 fallback 到其他节点），
        避免 silent bug 让策略效果被盖住。
        """
        nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("FixedNodeScheduler cannot schedule because cluster has no nodes")

        selected = self._find_node(nodes, self.preferred_node_name)

        if selected is None:
            available = [n.name for n in nodes]
            raise RuntimeError(
                f"FixedNodeScheduler target {self.preferred_node_name!r} not in cluster "
                f"(available: {available})"
            )

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


class CapacityAwareScheduler:
    """
    Capacity-Aware 调度器。

    每次调度选 capacity（cpu_millis）最大的节点，模拟"负载感知调度"。

    当有多个 pod 调度时：
    - 第一个 pod 选 capacity 最大的 server_1（8000 cpu_millis）
    - 第二个 pod 选 capacity 剩余最大的（仍是 server_1，因为只扣减部分）
    - 第三个 pod 才落到 server_2 或 server_3

    本样例只有 2 个 replica，2 个都落在 server_1 上。
    """

    def __init__(self, cluster_context: ClusterContext):
        """
        初始化调度器。
        """
        self.cluster_context = cluster_context

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating CapacityAwareScheduler for batch experiment")
        return CapacityAwareScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为待调度 Pod 选择 capacity 最大的节点。
        """
        nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("CapacityAwareScheduler cannot schedule because cluster has no nodes")

        # 按 allocatable.cpu_millis（= capacity - 已分配）降序选
        def remaining_cpu(node):
            try:
                return float(node.allocatable.cpu_millis)
            except AttributeError:
                try:
                    return float(node.capacity.cpu_millis)
                except AttributeError:
                    return 0.0

        selected = max(nodes, key=remaining_cpu)
        needed_images = self._needed_images(pod, selected)

        self.cluster_context.place_pod_on_node(pod, selected)

        logger.info(
            "CapacityAwareScheduler selected node=%s for pod=%s needed_images=%s remaining_cpu=%.0f",
            selected.name,
            pod.name,
            needed_images,
            remaining_cpu(selected),
        )

        return SchedulingResult(
            suggested_host=selected,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )

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
