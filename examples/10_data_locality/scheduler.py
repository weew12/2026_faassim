"""
文件作用：data_locality 样例使用的调度器。

本文件包含两个调度器：
1. InstrumentedDataLocalityScheduler：保留 Skippy 默认调度语义，并记录数据本地性候选节点信息；
2. ForcedNodeScheduler：强制调度到指定远端节点，用作对比基线。

通过两组实验可以观察：
- 数据本地性调度通常选择更靠近数据的节点；
- 强制远端调度会导致更长的数据下载时间。
"""

import logging
from typing import List, Optional

from skippy.core.model import Pod, Node, SchedulingResult
from skippy.core.scheduler import Scheduler
from skippy.core.utils import normalize_image_name

from sim.core import Environment

logger = logging.getLogger(__name__)


class InstrumentedDataLocalityScheduler(Scheduler):
    """
    可观测数据本地性调度器。

    该调度器继承 Skippy 原生 Scheduler，保留默认谓词和默认优先级。
    Skippy 默认优先级中已经包含 DataLocalityPriority，因此本类只额外记录候选节点信息。
    """

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating InstrumentedDataLocalityScheduler")
        return InstrumentedDataLocalityScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为 Pod 选择目标节点，并记录数据本地性候选信息。
        """
        nodes: List[Node] = self.cluster_context.list_nodes()
        feasible_nodes = [node for node in nodes if self.passes_predicates(pod, node)]

        self._log_data_locality_candidates(pod, feasible_nodes)

        result = super().schedule(pod)

        selected_node = result.suggested_host.name if result.suggested_host is not None else None

        logger.info(
            "data locality scheduler result pod=%s selected_node=%s feasible_nodes=%s needed_images=%s",
            pod.name,
            selected_node,
            result.feasible_nodes,
            result.needed_images,
        )

        env = getattr(self.cluster_context, "env", None)
        if env is not None and getattr(env, "metrics", None) is not None:
            env.metrics.log(
                "data_locality_scheduler_result",
                {
                    "feasible_nodes": result.feasible_nodes,
                    "needed_images_count": len(result.needed_images or []),
                },
                scheduler="data_locality_aware",
                pod_name=pod.name,
                selected_node=selected_node,
                needed_images=";".join(result.needed_images or []),
            )

        return result

    def _log_data_locality_candidates(self, pod: Pod, feasible_nodes: List[Node]):
        """
        记录每个可行候选节点到输入数据存储节点的估计传输代价。
        """
        env = getattr(self.cluster_context, "env", None)
        if env is None or getattr(env, "metrics", None) is None:
            return

        data_path = pod.spec.labels.get("data.skippy.io/receives-from-storage/path")
        data_size = pod.spec.labels.get("data.skippy.io/receives-from-storage")

        if not data_path:
            return

        storage_nodes = self.cluster_context.get_storage_nodes(data_path)

        for node in feasible_nodes:
            best_storage = None
            best_bandwidth = None
            estimated_download_time = None

            for storage_node in storage_nodes:
                if storage_node == node.name:
                    best_storage = storage_node
                    best_bandwidth = None
                    estimated_download_time = 0
                    break

                bandwidth = self.cluster_context.get_dl_bandwidth(storage_node, node.name)
                if best_bandwidth is None or bandwidth > best_bandwidth:
                    best_bandwidth = bandwidth
                    best_storage = storage_node

            data_item = self.cluster_context.storage_index.stat(*data_path.split("/"))
            if data_item is not None and best_bandwidth:
                estimated_download_time = data_item.size / best_bandwidth

            env.metrics.log(
                "data_locality_candidate",
                {
                    "estimated_download_time": estimated_download_time,
                    "best_bandwidth_bytes_per_s": best_bandwidth,
                },
                scheduler="data_locality_aware",
                pod_name=pod.name,
                candidate_node=node.name,
                data_path=data_path,
                data_size=data_size,
                storage_node=best_storage,
            )


class ForcedNodeScheduler:
    """
    强制节点调度器。

    该调度器用于构造远端调度对比组，不使用数据本地性打分。
    """

    def __init__(self, cluster_context, target_node_name: str):
        """
        初始化强制节点调度器。
        """
        self.cluster_context = cluster_context
        self.target_node_name = target_node_name

    @staticmethod
    def create(env: Environment, target_node_name: str = "edge_far"):
        """
        faas-sim 调用的调度器工厂方法。
        """
        logger.info("creating ForcedNodeScheduler target_node=%s", target_node_name)
        return ForcedNodeScheduler(env.cluster, target_node_name)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        直接把 Pod 调度到指定节点，并写回 ClusterContext。
        """
        nodes = self.cluster_context.list_nodes()
        target: Optional[Node] = None

        for node in nodes:
            if node.name == self.target_node_name:
                target = node
                break

        if target is None:
            raise RuntimeError(f"target node not found: {self.target_node_name}")

        needed_images = []
        host_images = self.cluster_context.images_on_nodes[target.name]
        for container in pod.spec.containers:
            image_name = normalize_image_name(container.image)
            if image_name not in host_images:
                needed_images.append(image_name)

        self.cluster_context.place_pod_on_node(pod, target)

        logger.info(
            "forced node scheduler result pod=%s selected_node=%s needed_images=%s",
            pod.name,
            target.name,
            needed_images,
        )

        env = getattr(self.cluster_context, "env", None)
        if env is not None and getattr(env, "metrics", None) is not None:
            env.metrics.log(
                "data_locality_scheduler_result",
                {
                    "feasible_nodes": len(nodes),
                    "needed_images_count": len(needed_images),
                },
                scheduler="forced_remote",
                pod_name=pod.name,
                selected_node=target.name,
                needed_images=";".join(needed_images),
            )

        return SchedulingResult(
            suggested_host=target,
            feasible_nodes=len(nodes),
            needed_images=needed_images,
        )
