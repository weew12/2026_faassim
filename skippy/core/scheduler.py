"""Skippy 调度器主流程。

本文件实现一个轻量 Kubernetes 风格调度器：
1. 从 ClusterContext 获取候选节点；
2. 执行谓词过滤，得到资源和标签约束均满足的可行节点；
3. 对可行节点执行多个优先级函数；
4. 将各优先级分数按权重求和；
5. 选择总分最高的节点，并更新 ClusterContext 中的 Pod 放置、节点剩余资源和镜像缓存状态。

在 faas-sim 中，``DefaultFaasSystem`` 创建函数副本后，会通过 ``sim/skippy.py`` 构造 Pod，
再调用本调度器决定函数副本部署在哪个 Ether/Skippy 节点上。
"""

import logging
from itertools import islice, cycle
from operator import itemgetter, add
from typing import List, Tuple

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, SchedulingResult
from skippy.core.predicates import Predicate, PodFitsResourcesPred, CheckNodeLabelPresencePred
from skippy.core.priorities import Priority, BalancedResourcePriority,     LatencyAwareImageLocalityPriority, CapabilityPriority, DataLocalityPriority, LocalityTypePriority
from skippy.core.utils import normalize_image_name

# 模块级日志器，用于输出调度过滤和打分细节。
logger = logging.getLogger(__name__)


class Scheduler:
    """    Skippy 调度器。

    业务职责：
    - 管理谓词集合和优先级函数集合；
    - 按 Kubernetes 风格执行“过滤 + 打分 + 选择最高分节点”；
    - 将调度结果写回 ClusterContext，使后续调度看到更新后的资源和镜像状态；
    - 返回 faas-sim 部署阶段所需的 ``SchedulingResult``。
    """

    # 默认谓词：资源必须足够，并且普通函数不能调度到存储专用节点。
    default_predicates: List[Predicate] = [
        PodFitsResourcesPred(),
        CheckNodeLabelPresencePred(['data.skippy.io/storage'], False)
    ]

    # 默认优先级函数：综合考虑资源均衡、镜像拉取代价、边缘优先、数据本地性和能力匹配。
    default_priorities: List[Tuple[float, Priority]] = [(1.0, BalancedResourcePriority()),
                                                        (1.0, LatencyAwareImageLocalityPriority()),
                                                        (1.0, LocalityTypePriority()),
                                                        (1.0, DataLocalityPriority()),
                                                        (1.0, CapabilityPriority())]

    # Kubernetes 风格参数：至少寻找的可行节点数量。
    min_feasible_nodes_to_find = 100

    # Kubernetes 风格参数：至少寻找的可行节点比例。
    min_feasible_nodes_percentage_to_find = 5

    # Kubernetes 风格参数：默认参与打分的节点比例。
    default_percentage_of_nodes_to_score = 50

    def __init__(self, cluster_context: ClusterContext, percentage_of_nodes_to_score: int = 100,
                 predicates: List[Predicate] = None,
                 priorities: List[Tuple[float, Priority]] = None):
        """        初始化调度器。

        参数：
        - ``cluster_context``：集群运行态上下文，提供节点、资源、镜像、带宽和存储索引；
        - ``percentage_of_nodes_to_score``：通过过滤后参与打分的节点比例；
        - ``predicates``：自定义谓词集合；为空时使用默认谓词；
        - ``priorities``：自定义优先级函数及权重；为空时使用默认优先级。
        """
        if priorities is None:
            priorities = self.default_priorities
        if predicates is None:
            predicates = self.default_predicates

        # 谓词集合，决定哪些节点能进入打分阶段。
        self.predicates = predicates
        # 优先级集合，每个元素为 (权重, 优先级函数实例)。
        self.priorities = priorities
        # 参与打分的可行节点比例，用于大规模集群中降低调度开销。
        self.percentage_of_nodes_to_score = percentage_of_nodes_to_score

        # 集群上下文，调度器所有状态查询和状态更新都通过它完成。
        self.cluster_context = cluster_context

        # 上一轮可行节点扫描停止位置；下一轮从这里继续，避免始终从第一个节点开始造成偏置。
        self.last_scored_node_index = 0

    def schedule(self, pod: Pod) -> SchedulingResult:
        """        为 Pod 选择部署节点。

        关键流程：
        1. 获取集群节点列表，并计算本轮最多需要找到多少可行节点；
        2. 从上一轮扫描位置开始，循环遍历节点并执行谓词过滤；
        3. 对可行节点逐个执行优先级函数，并按权重累加得分；
        4. 选择总分最高的节点；
        5. 计算该节点缺失的镜像列表；
        6. 调用 ``place_pod_on_node`` 更新集群上下文；
        7. 返回 ``SchedulingResult``。
        """
        logging.debug('Received a new pod to schedule: %s', pod.name)

        nodes = self.cluster_context.list_nodes()
        num_of_nodes_to_find = self.__num_feasible_nodes_to_find(len(nodes))

        # 从 last_scored_node_index 开始循环扫描节点，找到满足所有谓词的候选节点。
        filtered = filter(lambda node: self.passes_predicates(pod, node),
                          islice(cycle(nodes), self.last_scored_node_index, self.last_scored_node_index + len(nodes)))
        feasible_nodes: [Node] = list(islice(filtered, num_of_nodes_to_find))
        if len(feasible_nodes) > 0:
            self.last_scored_node_index = (nodes.index(feasible_nodes[-1]) + 1) % len(nodes)

        cluster = self.cluster_context

        # 对所有可行节点执行加权优先级打分。
        scored_nodes: [int] = [0] * len(feasible_nodes)
        for weighted_priority in self.priorities:
            weight = weighted_priority[0]
            function = weighted_priority[1]
            # map 阶段：每个节点独立计算原始分数或代价。
            mapped_nodes = [function.map_node_score(cluster, pod, node) for node in feasible_nodes]
            # reduce 阶段：基于所有节点结果做归一化或反向缩放。
            reduced_node_scores = function.reduce_mapped_score(cluster, pod, feasible_nodes, mapped_nodes)
            # 应用权重后累加到节点总分。
            weighted_node_scores = [score * weight for score in reduced_node_scores]
            scored_nodes = list(map(add, weighted_node_scores, scored_nodes))

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('Pod %s / %s: %s', pod.name, type(function), weighted_node_scores)

        scored_named_nodes: [(Node, int)] = list(zip(feasible_nodes, scored_nodes))

        logging.debug('Node scores: %s', scored_named_nodes)

        # 选择总分最高的节点；没有可行节点时 suggested_host 为 None。
        sorted_scored_nodes = max(scored_named_nodes, key=itemgetter(1), default=(None, 0))
        suggested_host: Node = next(iter(sorted_scored_nodes), None)
        needed_images = None

        if suggested_host is not None:
            # 在写回调度状态之前，记录目标节点尚未缓存的镜像，供 faas-sim 模拟镜像拉取。
            needed_images = []
            host_images = self.cluster_context.images_on_nodes[suggested_host.name]
            for container in pod.spec.containers:
                if normalize_image_name(container.image) not in host_images:
                    needed_images.append(normalize_image_name(container.image))

            # 将调度结果写回上下文：扣减资源、登记 Pod、更新镜像缓存表。
            self.cluster_context.place_pod_on_node(pod, suggested_host)
            logging.debug('Found best node. Remaining allocatable resources after scheduling: %s',
                          suggested_host.allocatable)

        return SchedulingResult(suggested_host=suggested_host, feasible_nodes=len(feasible_nodes),
                                needed_images=needed_images)

    def passes_predicates(self, pod: Pod, node: Node) -> bool:
        """判断 Pod 是否通过当前调度器配置的所有谓词。"""
        return all(self.__passes_and_logs_predicate(predicate, self.cluster_context, pod, node)
                   for predicate in self.predicates)

    def __passes_and_logs_predicate(self, predicate: Predicate, context: ClusterContext, pod: Pod, node: Node):
        """执行单个谓词，并在 debug 模式下记录通过/失败状态。"""
        result = predicate.passes_predicate(context, pod, node)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Pod {pod.name} / Node {node.name} / {type(predicate).__name__}: '
                         f'{"Passed" if result else "Failed"}')
        return result

    def __num_feasible_nodes_to_find(self, num_all_nodes: int) -> int:
        """        计算本轮调度需要收集多少个可行节点参与打分。

        业务作用：
        Kubernetes 在大规模集群中不会总是为所有节点打分，而是根据集群规模和配置比例选择
        一部分可行节点。该函数保留这一思想，既支持完整打分，也支持降低调度开销。
        """
        if num_all_nodes < self.min_feasible_nodes_percentage_to_find or self.percentage_of_nodes_to_score >= 100:
            return num_all_nodes
        adaptive_percentage: float = self.percentage_of_nodes_to_score
        if adaptive_percentage <= 0:
            adaptive_percentage = self.default_percentage_of_nodes_to_score - num_all_nodes / 125
            if adaptive_percentage < self.min_feasible_nodes_percentage_to_find:
                adaptive_percentage = self.min_feasible_nodes_percentage_to_find
        num_nodes = int(num_all_nodes * adaptive_percentage / 100)
        if num_nodes < self.min_feasible_nodes_to_find:
            return self.min_feasible_nodes_to_find
        return num_nodes
