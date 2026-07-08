"""
文件作用：可观测 Skippy 默认调度器。

该文件在 Skippy 原生 Scheduler 基础上增加指标记录。
调度决策仍由 Skippy 默认谓词和默认优先级完成，本样例只额外记录：
- 候选节点数量；
- 通过资源过滤的节点数量；
- 各候选节点的资源状态；
- 调度结果中的 suggested_host、feasible_nodes、needed_images。
"""

import logging
from typing import List

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, SchedulingResult
from skippy.core.scheduler import Scheduler

from sim.core import Environment

logger = logging.getLogger(__name__)


class InstrumentedSkippyScheduler(Scheduler):
    """
    可观测 Skippy 调度器。

    业务职责：
    - 继承 Skippy 原生 Scheduler；
    - 保留默认谓词和默认优先级；
    - 在 schedule 前记录候选节点和资源过滤状态；
    - 在 schedule 后记录 SchedulingResult；
    - 帮助用户理解默认调度器如何完成资源过滤、节点选择和镜像拉取判断。
    """

    max_candidate_log_rows = 30

    def __init__(self, cluster_context: ClusterContext, percentage_of_nodes_to_score: int = 100):
        """
        初始化可观测调度器。

        参数：
        - cluster_context：Skippy 集群上下文；
        - percentage_of_nodes_to_score：参与打分的节点比例。
        """
        super().__init__(
            cluster_context=cluster_context,
            percentage_of_nodes_to_score=percentage_of_nodes_to_score,
        )

    @staticmethod
    def create(env: Environment):
        """
        faas-sim 使用的调度器工厂方法。

        参数：
        - env：faas-sim 运行时环境。

        返回：
        - InstrumentedSkippyScheduler：可观测 Skippy 调度器实例。
        """
        logger.info("creating InstrumentedSkippyScheduler")
        return InstrumentedSkippyScheduler(env.cluster)

    def schedule(self, pod: Pod) -> SchedulingResult:
        """
        为 Pod 选择目标节点，并记录调度过程。

        参数：
        - pod：待调度 Pod。

        返回：
        - SchedulingResult：Skippy 原生调度结果。
        """
        env = getattr(self.cluster_context, "env", None)
        nodes: List[Node] = self.cluster_context.list_nodes()

        feasible_nodes = []
        for node in nodes:
            passed = self.passes_predicates(pod, node)
            if passed:
                feasible_nodes.append(node)

        logger.info(
            "skippy scheduling pod=%s, all_nodes=%d, feasible_nodes=%d",
            pod.name,
            len(nodes),
            len(feasible_nodes),
        )

        if env is not None and getattr(env, "metrics", None) is not None:
            self._log_candidate_snapshot(env, pod, nodes, feasible_nodes)

        # 调度前 probe：用于和 invocations.csv 的 simtime 关联做 join 验证
        simtime_before = float(getattr(env, "now", 0.0)) if env is not None else 0.0
        if env is not None and getattr(env, "metrics", None) is not None:
            env.metrics.log(
                "schedule_probe",
                {
                    "simtime": simtime_before,
                    "feasible_nodes_count": len(feasible_nodes),
                    "all_nodes_count": len(nodes),
                    "phase": "before",
                },
                pod_name=pod.name,
            )

        # 调用 Skippy 原生 schedule。该调用会执行过滤、打分、选择节点，并写回 ClusterContext。
        result = super().schedule(pod)

        selected_node = result.suggested_host.name if result.suggested_host is not None else None
        needed_images = result.needed_images or []

        logger.info(
            "skippy result pod=%s, selected_node=%s, returned_feasible_nodes=%s, needed_images=%s",
            pod.name,
            selected_node,
            result.feasible_nodes,
            needed_images,
        )

        simtime_after = float(getattr(env, "now", 0.0)) if env is not None else 0.0
        if env is not None and getattr(env, "metrics", None) is not None:
            env.metrics.log(
                "skippy_scheduler_result",
                {
                    "all_nodes": len(nodes),
                    "feasible_nodes_full": len(feasible_nodes),
                    "returned_feasible_nodes": result.feasible_nodes,
                    "needed_images_count": len(needed_images),
                    "simtime": simtime_after,
                },
                pod_name=pod.name,
                selected_node=selected_node,
                needed_images=";".join(needed_images),
            )
            # 调度后 probe：携带最终 selected_node + needed_images_count
            env.metrics.log(
                "schedule_probe",
                {
                    "simtime": simtime_after,
                    "feasible_nodes_count": len(feasible_nodes),
                    "all_nodes_count": len(nodes),
                    "selected_node": selected_node,
                    "needed_images_count": len(needed_images),
                    "phase": "after",
                },
                pod_name=pod.name,
            )

        return result

    def _log_candidate_snapshot(self, env: Environment, pod: Pod, nodes: List[Node], feasible_nodes: List[Node]):
        """
        记录候选节点快照。

        为避免城市感知拓扑节点过多导致输出太大，本函数只记录前 max_candidate_log_rows 个节点。
        """
        feasible_names = {node.name for node in feasible_nodes}

        for index, node in enumerate(nodes[:self.max_candidate_log_rows]):
            env.metrics.log(
                "skippy_scheduler_candidate",
                {
                    "candidate_index": index,
                    "cpu_capacity": node.capacity.cpu_millis,
                    "cpu_allocatable": node.allocatable.cpu_millis,
                    "mem_capacity": node.capacity.memory,
                    "mem_allocatable": node.allocatable.memory,
                    "passed_predicates": node.name in feasible_names,
                    "is_storage_node": "data.skippy.io/storage" in node.labels,
                },
                pod_name=pod.name,
                node_name=node.name,
                arch=node.labels.get("beta.kubernetes.io/arch"),
                node_type=node.labels.get("ether.edgerun.io/type"),
            )
