"""Skippy 调度谓词实现。

谓词对应调度流程中的“过滤阶段”：在对节点打分之前，先判断一个 Pod 是否具备放置到
某个节点上的基本条件。只有通过所有谓词的节点才会进入优先级打分。

当前内置谓词主要覆盖两类逻辑：
1. 资源充足性：节点剩余 CPU/内存是否能承载 Pod；
2. 标签存在性：节点是否包含或不包含某些标签，例如避免把普通函数调度到存储专用节点。
"""

import logging
from typing import List

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, Capacity

# 模块级日志器，用于在 debug 模式下输出每个谓词的通过/失败原因。
logger = logging.getLogger(__name__)


class Predicate:
    """    调度谓词基类。

    子类需要实现 ``passes_predicate``，返回 ``True`` 表示 Pod 可以继续考虑该节点，
    返回 ``False`` 表示该节点被过滤掉。
    """

    def __init__(self):
        """谓词基类不持有状态。"""
        pass

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """判断 Pod 是否能通过指定节点的过滤条件。"""
        raise NotImplementedError


class CombinedPredicate(Predicate):
    """    组合谓词。

    业务作用：
    将多个谓词按逻辑与组合，只有所有子谓词均通过时才返回通过。该类用于构造
    ``GeneralPreds``、``EssentialPreds`` 等 Kubernetes 风格的谓词集合。
    """

    def __init__(self, predicates: [Predicate]):
        """保存待组合的子谓词列表。"""
        super().__init__()
        # 子谓词集合，执行时按顺序逐个判断。
        self.predicates = predicates

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """执行所有子谓词，任一失败则整体失败。"""
        return all(self.__passes_and_logs_predicate(predicate, context, pod, node)
                   for predicate in self.predicates)

    def __passes_and_logs_predicate(self, predicate: Predicate, context: ClusterContext, pod: Pod, node: Node):
        """执行单个子谓词，并在 debug 日志中记录结果。"""
        result = predicate.passes_predicate(context, pod, node)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Pod {pod.name} / Node {node.name} / {type(predicate).__name__}: '
                         f'{"Passed" if result else "Failed"}')

        return result


class PodFitsResourcesPred(Predicate):
    """    资源充足性谓词。

    业务作用：
    计算 Pod 中所有容器声明的 CPU/内存请求总和，并与目标节点的剩余可分配资源比较。
    若请求量不超过节点剩余资源，则该节点可承载该 Pod；否则该节点在过滤阶段被排除。
    """

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """判断目标节点剩余 CPU/内存是否满足 Pod 资源请求。"""
        # 节点当前剩余可分配资源，会随已有 Pod 放置动态变化。
        allocatable = node.allocatable
        # 累加 Pod 内容器的资源请求。
        requested = Capacity(0, 0)
        for container in pod.spec.containers:
            requested.cpu_millis += container.resources.requests.get('cpu', container.resources.
                                                                     default_milli_cpu_request)
            requested.memory += container.resources.requests.get('memory', container.resources.default_mem_request)
        # CPU 与内存两个维度都满足时才通过。
        passed = requested.memory <= allocatable.memory and requested.cpu_millis <= allocatable.cpu_millis

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Pod {pod.name} requests {requested.cpu_millis} / {requested.memory}. '
                         f'Available on node {node.name}: {allocatable.cpu_millis} / {allocatable.memory}.'
                         f'Passed: {passed}')
        return passed


class NonCriticalPreds(CombinedPredicate):
    """非关键 Pod 谓词集合。当前仿真不区分关键/非关键 Pod，因此仅包含资源充足性检查。"""

    def __init__(self):
        """构造非关键 Pod 谓词集合。"""
        super().__init__([PodFitsResourcesPred()])


class EssentialPreds(CombinedPredicate):
    """基础谓词集合。当前实现同样包含资源充足性检查。"""

    def __init__(self):
        """构造基础谓词集合。"""
        super().__init__([PodFitsResourcesPred()])


class GeneralPreds(CombinedPredicate):
    """    通用谓词集合。

    业务作用：
    模拟 Kubernetes 默认调度器中的 GeneralPredicates 组合。faas-sim 当前没有关键 Pod
    概念，因此将 EssentialPreds 和 NonCriticalPreds 都纳入逻辑与判断。
    """

    def __init__(self):
        """构造通用谓词集合。"""
        super().__init__([EssentialPreds(), NonCriticalPreds()])


class CheckNodeLabelPresencePred(Predicate):
    """    节点标签存在性谓词。

    业务作用：
    判断目标节点是否必须包含或必须不包含某些标签。默认调度器使用该谓词避免把普通
    函数 Pod 放到带有 ``data.skippy.io/storage`` 标签的存储节点上。
    """

    def __init__(self, labels: List[str], should_be_present=True) -> None:
        """        初始化标签存在性谓词。

        参数：
        - ``labels``：需要检查的标签键列表；
        - ``should_be_present``：为 True 时要求标签存在，为 False 时要求标签不存在。
        """
        super().__init__()
        # 待检查的节点标签键集合。
        self.labels = labels
        # True 表示必须存在，False 表示必须不存在。
        self.should_be_present = should_be_present

        # 根据模式绑定具体检查函数，避免 passes_predicate 中反复分支判断。
        if should_be_present:
            self._passes_predicate = self.has_labels
        else:
            self._passes_predicate = self.has_labels_not

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """执行标签存在性判断。"""
        return self._passes_predicate(node)

    def has_labels(self, node: Node) -> bool:
        """要求节点同时包含所有指定标签。"""
        for label in self.labels:
            if label not in node.labels:
                return False

        return True

    def has_labels_not(self, node: Node) -> bool:
        """要求节点不包含任何指定标签。"""
        for label in self.labels:
            if label in node.labels:
                return False

        return True
