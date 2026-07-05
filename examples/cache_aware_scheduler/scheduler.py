"""
文件作用：缓存状态感知调度器。

该文件提供两个稳定可复现的调度器：
- CacheBlindScheduler：不读取缓存状态，作为缓存无感知基线；
- CacheAwareScheduler：读取节点级函数 warm 缓存状态，并优先选择已有目标函数缓存的节点。

说明：
早期版本尝试直接封装默认 Skippy 调度器作为 baseline。但在本样例中一次性部署多个函数时，
默认 Skippy 可能因为候选节点资源过滤、镜像局部性评分或内部队列状态导致某个函数副本长期
无法进入 RUNNING，进而卡在 poll_available_replica。为了保证样例稳定运行，本版使用
cache-blind baseline 对比 cache-aware scheduler，重点观察“是否使用缓存状态”带来的差异。
"""

import logging
from typing import Optional

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, SchedulingResult
from skippy.core.utils import normalize_image_name

from sim.core import Environment

from cache_state import CacheStateIndex

logger = logging.getLogger(__name__)


class CacheBlindScheduler:
    """
    缓存无感知基线调度器。

    该调度器不读取函数缓存状态，只按 server 节点顺序轮转选择目标节点。
    它用于形成稳定的对照组，避免默认 Skippy 在小型样例中因资源过滤导致副本长期 Pending。
    """

    def __init__(self, cluster_context: ClusterContext):
        """
        初始化调度器。
        """
        self.cluster_context = cluster_context
        self.cursor = 0

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating CacheBlindScheduler")
        return CacheBlindScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为 Pod 选择目标节点。
        """
        nodes = self._server_nodes()

        if not nodes:
            nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("CacheBlindScheduler cannot schedule because cluster has no nodes")

        function_name = self._infer_function_name(pod)
        selected_node = nodes[self.cursor % len(nodes)]
        self.cursor += 1

        needed_images = self._needed_images(pod, selected_node)
        self.cluster_context.place_pod_on_node(pod, selected_node)

        logger.info(
            "CacheBlindScheduler selected function=%s pod=%s node=%s",
            function_name,
            pod.name,
            selected_node.name,
        )

        self._log_result(pod, function_name, selected_node, needed_images)

        return SchedulingResult(
            suggested_host=selected_node,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )

    def _server_nodes(self):
        """
        返回 server 节点列表。
        """
        return [
            node for node in self.cluster_context.list_nodes()
            if str(node.name).startswith("server")
        ]

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

    @staticmethod
    def _infer_function_name(pod: Pod) -> str:
        """
        从 Pod 中推断函数名称。
        """
        labels = getattr(getattr(pod, "spec", None), "labels", {}) or {}
        if "cache.edgerun.io/function" in labels:
            return str(labels["cache.edgerun.io/function"])
        return str(getattr(pod, "name", "unknown"))

    def _log_result(self, pod: Pod, function_name: str, selected_node: Node, needed_images):
        """
        记录调度结果。
        """
        env = getattr(self.cluster_context, "env", None)
        if env is None or getattr(env, "metrics", None) is None:
            return

        env.metrics.log(
            "cache_aware_scheduler_result",
            {
                "cache_hit": False,
                "selected_score": 0.0,
                "needed_images_count": len(needed_images),
            },
            function_name=function_name,
            pod_name=pod.name,
            selected_node=selected_node.name,
            scheduler="cache_blind",
            needed_images=";".join(needed_images or []),
        )


class CacheAwareScheduler:
    """
    缓存状态感知调度器。

    打分思路：
    - 目标节点已有目标函数 warm 实例时，获得较高 cache_hit_bonus；
    - 缓存越新，获得更高 freshness_score；
    - 节点当前 Pod 数越少，获得更高 load_score；
    - 调度器选择总分最高的候选节点。
    """

    def __init__(
        self,
        cluster_context: ClusterContext,
        cache_index: CacheStateIndex,
        cache_hit_weight: float = 10.0,
        freshness_weight: float = 1.0,
        load_weight: float = 0.2,
    ):
        """
        初始化调度器。
        """
        self.cluster_context = cluster_context
        self.cache_index = cache_index
        self.cache_hit_weight = cache_hit_weight
        self.freshness_weight = freshness_weight
        self.load_weight = load_weight

    @staticmethod
    def create(env: Environment, cache_index: CacheStateIndex):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating CacheAwareScheduler")
        return CacheAwareScheduler(env.cluster, cache_index)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为 Pod 选择目标节点。
        """
        nodes = self._server_nodes()

        if not nodes:
            nodes = self.cluster_context.list_nodes()

        if not nodes:
            raise RuntimeError("CacheAwareScheduler cannot schedule because cluster has no nodes")

        function_name = self._infer_function_name(pod)
        scored_nodes = []

        for node in nodes:
            score_detail = self._score_node(function_name, node)
            scored_nodes.append(score_detail)
            self._log_candidate(pod, function_name, node, score_detail)

        scored_nodes.sort(key=lambda item: item["total_score"], reverse=True)
        selected_detail = scored_nodes[0]
        selected_node = selected_detail["node"]

        needed_images = self._needed_images(pod, selected_node)
        self.cluster_context.place_pod_on_node(pod, selected_node)

        logger.info(
            "CacheAwareScheduler selected function=%s pod=%s node=%s score=%.4f cache_hit=%s",
            function_name,
            pod.name,
            selected_node.name,
            selected_detail["total_score"],
            selected_detail["cache_hit"],
        )

        self._log_result(pod, function_name, selected_node, selected_detail, needed_images)

        return SchedulingResult(
            suggested_host=selected_node,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )

    def _server_nodes(self):
        """
        返回 server 节点列表。
        """
        return [
            node for node in self.cluster_context.list_nodes()
            if str(node.name).startswith("server")
        ]

    def _score_node(self, function_name: str, node: Node):
        """
        计算候选节点得分。
        """
        cache_entry = self.cache_index.entry_for_node(function_name, node.name)

        cache_hit = cache_entry is not None
        cache_hit_score = self.cache_hit_weight if cache_hit else 0.0

        freshness_score = 0.0
        avg_cold_start = 0.0
        if cache_entry is not None:
            freshness_score = self.freshness_weight / (1.0 + cache_entry.last_access_age)
            avg_cold_start = cache_entry.avg_cold_start

        pod_count = self._node_pod_count(node.name)
        load_score = self.load_weight / (1.0 + pod_count)

        total_score = cache_hit_score + freshness_score + load_score

        return {
            "node": node,
            "function_name": function_name,
            "cache_hit": cache_hit,
            "cache_hit_score": cache_hit_score,
            "freshness_score": freshness_score,
            "load_score": load_score,
            "total_score": total_score,
            "pod_count": pod_count,
            "avg_cold_start": avg_cold_start,
        }

    def _node_pod_count(self, node_name: str) -> int:
        """
        返回节点上已放置 Pod 数。
        """
        try:
            return len(self.cluster_context.pods_on_nodes[node_name])
        except Exception:
            return 0

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

    def _infer_function_name(self, pod: Pod) -> str:
        """
        从 Pod 中推断函数名称。
        """
        labels = getattr(getattr(pod, "spec", None), "labels", {}) or {}

        for key in [
            "cache.edgerun.io/function",
            "faas_function",
            "function_name",
            "function",
        ]:
            if key in labels:
                return str(labels[key])

        return str(getattr(pod, "name", "unknown"))

    def _log_candidate(self, pod: Pod, function_name: str, node: Node, score_detail):
        """
        记录候选节点得分。
        """
        env = getattr(self.cluster_context, "env", None)
        if env is None or getattr(env, "metrics", None) is None:
            return

        env.metrics.log(
            "cache_aware_candidate",
            {
                "cache_hit": score_detail["cache_hit"],
                "cache_hit_score": score_detail["cache_hit_score"],
                "freshness_score": score_detail["freshness_score"],
                "load_score": score_detail["load_score"],
                "total_score": score_detail["total_score"],
                "pod_count": score_detail["pod_count"],
                "avg_cold_start": score_detail["avg_cold_start"],
            },
            function_name=function_name,
            pod_name=pod.name,
            candidate_node=node.name,
            scheduler="cache_aware",
        )

    def _log_result(self, pod: Pod, function_name: str, selected_node: Node, selected_detail, needed_images):
        """
        记录调度结果。
        """
        env = getattr(self.cluster_context, "env", None)
        if env is None or getattr(env, "metrics", None) is None:
            return

        env.metrics.log(
            "cache_aware_scheduler_result",
            {
                "cache_hit": selected_detail["cache_hit"],
                "selected_score": selected_detail["total_score"],
                "needed_images_count": len(needed_images),
            },
            function_name=function_name,
            pod_name=pod.name,
            selected_node=selected_node.name,
            scheduler="cache_aware",
            needed_images=";".join(needed_images or []),
        )
