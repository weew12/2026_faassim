"""Skippy 调度优先级函数。

优先级函数对应调度流程中的“打分阶段”：经过谓词过滤后的可行节点，会根据多个
优先级函数计算分数。调度器对各优先级函数的分数乘以权重并求和，最终选择总分最高
的节点作为建议放置位置。

本文件既包含 Kubernetes 默认调度器思想中的资源均衡、镜像本地性，也包含 Skippy 面向
边缘/数据密集型场景扩展的数据本地性、位置类型和硬件能力评分。
"""

import logging
from math import fabs
from typing import Dict

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node, Capacity, ImageState
from skippy.core.utils import normalize_image_name

# 模块级日志器，用于观察每个优先级函数的打分过程。
logger = logging.getLogger(__name__)


def _scale_scores(scores, t_max=10):
    """    将原始分数线性缩放到 ``[0, t_max]``。

    业务作用：
    某些优先级函数先计算“匹配数量”或其他原始度量，再通过该函数映射到统一的
    Kubernetes 风格打分区间，便于与其他优先级函数加权求和。
    """
    r_min = min(scores, default=0)
    r_max = max(scores, default=0)

    div = r_max - r_min

    if div == 0:
        return [0] * len(scores)

    return [int(((x - r_min) / div) * t_max) for x in scores]


def _scale_scores_inverse(scores, t_max=10):
    """    将原始代价反向缩放到 ``[t_max, 0]``。

    业务作用：
    对于传输时间这类“越小越好”的代价指标，使用反向缩放，使低代价节点获得更高分。
    """
    r_min = min(scores, default=0)
    r_max = max(scores, default=0)

    div = r_min - r_max

    if div == 0:
        return [0] * len(scores)

    return [int(((x - r_max) / div) * t_max) for x in scores]


class Priority:
    """    优先级函数基类。

    子类通常实现两阶段打分：
    1. ``map_node_score``：为单个候选节点计算原始分数或代价；
    2. ``reduce_mapped_score``：基于所有候选节点的原始结果进行归一化或反向缩放。
    """

    def __init__(self):
        """优先级基类不持有状态。"""
        pass

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """计算单个候选节点对当前 Pod 的原始分数。"""
        raise NotImplementedError

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """        对所有候选节点的原始分数进行归约/归一化。

        默认实现不改变分数，适用于已经返回统一区间分数的优先级函数。
        """
        return node_scores


class EqualPriority(Priority):
    """所有节点给相同分数的占位优先级函数，常用于基线或调试。"""

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """返回固定分数 1。"""
        return 1


class ImageLocalityPriority(Priority):
    """    镜像本地性优先级函数。

    业务作用：
    倾向选择已经缓存目标镜像的节点，减少部署阶段拉取镜像的网络传输和冷启动等待。
    该函数与 Kubernetes ImageLocalityPriority 思路一致：节点已有镜像越大、镜像分布越广，
    本地命中价值越高。
    """

    # 字节换算基础单位。
    mb: int = 1024 * 1024
    # 小于该阈值的镜像本地性收益按最小阈值处理，避免过小镜像影响过低。
    min_threshold: int = 23 * mb
    # 大于该阈值的镜像本地性收益按最大阈值截断，避免超大镜像主导全部评分。
    max_threshold: int = 1000 * mb

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """计算目标节点已有镜像带来的本地性分数。"""
        return self.calculate_priority(context, self.sum_image_scores(context, pod, node))

    def calculate_priority(self, context: ClusterContext, sum_scores: int) -> int:
        """将镜像本地性原始收益映射到 ``[0, context.max_priority]``。"""
        if sum_scores < self.min_threshold:
            sum_scores = self.min_threshold
        elif sum_scores > self.max_threshold:
            sum_scores = self.max_threshold
        return int(context.max_priority * (sum_scores - self.min_threshold) / (self.max_threshold - self.min_threshold))

    def sum_image_scores(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """累计 Pod 所需镜像在目标节点上的本地命中收益。"""
        calc_sum = 0
        total_num_nodes = len(context.list_nodes())
        if pod.spec.containers is not Node:
            for container in pod.spec.containers:
                try:
                    image_state: ImageState = context.images_on_nodes[node.name][normalize_image_name(container.image)]
                    calc_sum += self.scaled_image_score(node, image_state, total_num_nodes)
                except KeyError:
                    # 节点没有缓存该镜像时不增加本地性收益。
                    pass
        return calc_sum

    def scaled_image_score(self, node: Node, image_state: ImageState, total_num_nodes: int) -> int:
        """根据镜像大小和镜像分布比例计算单镜像收益。"""
        spread = float(image_state.num_nodes) / float(total_num_nodes)
        return int(float(image_state.size[node.labels['beta.kubernetes.io/arch']]) * spread)


class ResourcePriority(Priority):
    """    资源类优先级函数基类。

    业务作用：
    统一计算 Pod 的资源请求总量，并把请求量与节点剩余资源交给子类的 ``scorer``。
    子类只需定义具体评分策略，例如资源均衡或资源剩余最大化。
    """

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """累加 Pod 资源请求，并调用子类 scorer 计算节点分数。"""
        logging.debug(f'ResourcePriority: Calculating score for {pod.name} on {node.name}')
        allocatable = node.allocatable
        requested = Capacity()
        requested.memory = 0
        requested.cpu_millis = 0
        for container in pod.spec.containers:
            requested.cpu_millis += container.resources.requests.get("cpu", container.resources.
                                                                     default_milli_cpu_request)
            requested.memory += container.resources.requests.get("memory", container.resources.default_mem_request)

        score = self.scorer(context, requested, allocatable)
        return score

    def scorer(self, context: ClusterContext, requested: Capacity, allocatable: Capacity):
        """由子类实现具体资源评分公式。"""
        raise NotImplementedError


class BalancedResourcePriority(ResourcePriority):
    """    资源均衡优先级函数。

    业务作用：
    倾向选择 CPU 与内存占用比例更均衡的节点，避免某一类资源先被耗尽而另一类资源大量
    闲置。分数越高表示请求放入该节点后 CPU/内存占比越接近。
    """

    def scorer(self, context: ClusterContext, requested: Capacity, allocatable: Capacity):
        """根据 CPU/内存请求占节点剩余资源的比例差计算均衡分。"""
        cpu_fraction = self.fraction_of_capacity(requested.cpu_millis, allocatable.cpu_millis)
        memory_fraction = self.fraction_of_capacity(requested.memory, allocatable.memory)

        # 若某一维资源请求已经超过或等于剩余容量，则该节点不应被优先选择。
        if cpu_fraction >= 1 or memory_fraction >= 1:
            return 0

        diff = fabs(cpu_fraction - memory_fraction)
        result = int((1 - diff) * float(context.max_priority))
        return result

    @staticmethod
    def fraction_of_capacity(requested: int, capacity: int) -> float:
        """计算请求量占容量的比例，容量为 0 时用 1 避免除零。"""
        if capacity == 0:
            capacity = 1
        return float(requested) / float(capacity)


class LocalityTypePriority(Priority):
    """    节点位置类型优先级函数。

    业务作用：
    倾向选择带有 ``locality.skippy.io/type=edge`` 标签的边缘节点，弱化云节点优先级。
    该策略适合边缘优先执行的 serverless edge 场景。
    """

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """根据节点 locality 标签返回边缘/云位置分。"""
        priority_mapping: Dict[str, int] = {
            'edge': context.max_priority,
            'cloud': 0
        }
        try:
            return priority_mapping.get(node.labels['locality.skippy.io/type'], 0)
        except KeyError:
            return 0


class CapabilityPriority(Priority):
    """    硬件/能力匹配优先级函数。

    业务作用：
    检查节点是否具备 Pod 标签声明的能力，例如 GPU、TPU 或其他边缘设备能力。匹配项越多，
    原始分越高；随后通过 reduce 阶段缩放到统一评分范围。
    """

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """计算节点能力标签与 Pod 需求标签的匹配数量。"""
        priority = 0
        # 只取 skippy 能力标签，避免普通标签干扰能力匹配。
        pod_caps = dict(filter(lambda label: 'capability.skippy.io' in label[0], node.labels.items()))
        for capability in pod_caps.items():
            if capability[0] in pod.spec.labels and capability[1] == pod.spec.labels[capability[0]]:
                priority += 1
        return priority

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """将能力匹配数量缩放到统一评分区间。"""
        return _scale_scores(node_scores, context.max_priority)


class LocalityPriority(Priority):
    """    本地性/距离类优先级基类。

    业务作用：
    将“需要传输的数据量”和“目标传输路径带宽”转换为传输时间代价。子类分别定义
    传输对象大小和目标节点，例如镜像仓库、输入数据存储节点或输出数据存储节点。
    """

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """计算该节点完成相关数据传输所需的估计时间。"""
        size = self.get_size(context, pod, node)
        target_node = self.get_target_node(context, pod, node)
        # 下载方向表示从目标节点到候选执行节点的传输，例如 registry -> worker。
        bandwidth = context.get_dl_bandwidth(target_node, node.name)
        time = int(size / bandwidth)
        return time

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """        将传输时间代价转换为优先级分数。

        传输时间越小越好，因此最高代价节点获得低分，最低代价节点获得高分。
        """
        min_count_by_node_name = min(node_scores, default=0)
        max_count_by_node_name = max(node_scores, default=0)
        if max_count_by_node_name == 0:
            return [0] * len(node_scores)
        result = list(map(lambda node_count: int(context.max_priority *
                                                 (max_count_by_node_name - node_count + min_count_by_node_name) /
                                                 max_count_by_node_name),
                          node_scores))
        return result

    def get_target_node(self, context: ClusterContext, pod: Pod, node: Node) -> str:
        """返回传输源节点或目标服务节点名称，由子类实现。"""
        raise NotImplemented()

    def get_size(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """返回需要传输的数据量，单位为字节，由子类实现。"""
        raise NotImplemented()


class LatencyAwareImageLocalityPriority(LocalityPriority):
    """    带宽感知镜像本地性优先级函数。

    业务作用：
    不仅判断节点是否已有镜像，还根据镜像仓库到候选节点的带宽估算拉取缺失镜像的时间。
    对于边缘环境中链路差异明显的场景，该函数比单纯 ImageLocality 更能体现部署代价。
    """

    def get_size(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """统计目标节点尚未缓存的镜像总大小。"""
        size = 0
        node_arch = node.labels['beta.kubernetes.io/arch']

        for container in pod.spec.containers:
            image_name = normalize_image_name(container.image)

            if image_name in context.images_on_nodes[node.name]:
                # 节点已有该镜像，不需要额外拉取。
                continue

            image_states = context.get_image_state(image_name)
            if node_arch not in image_states.size:
                replacement = list(image_states.size.keys())[0]
                logger.error("could not resolve node arch '%s' for image '%s', estimating using '%s' instead",
                             node_arch, image_name, replacement)
                node_arch = replacement

            size += context.get_image_state(image_name).size[node_arch]

        return size

    def get_target_node(self, context: ClusterContext, pod: Pod, node: Node) -> str:
        """镜像拉取的源节点固定为 registry。"""
        return 'registry'


class DataLocalityPriority(Priority):
    """    数据本地性优先级函数。

    业务作用：
    面向数据密集型 Serverless Edge 场景，估算函数输入数据读取和输出数据写回的网络传输
    时间。候选节点距离数据所在存储节点越近、带宽越高，传输时间越短，最终得分越高。

    Pod 通过标签声明数据路径：
    - ``data.skippy.io/receives-from-storage/path``：函数需要读取的对象路径；
    - ``data.skippy.io/sends-to-storage/path``：函数需要写回的对象路径。
    """

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """计算输入读取时间与输出写回时间之和，作为原始代价。"""
        # 当前模型假设每个函数至多声明一个输入对象和一个输出对象。
        total_time = 0
        total_time += self.calculate_recv_time(context, pod, node)
        total_time += self.calculate_send_time(context, pod, node)

        return total_time

    def calculate_recv_time(self, context: ClusterContext, pod: Pod, node: Node):
        """估算候选节点从存储节点读取输入对象所需时间。"""
        path = pod.spec.labels.get('data.skippy.io/receives-from-storage/path')

        if not path:
            return 0

        data_item = context.storage_index.stat(*path.split('/'))

        if not data_item:
            return 0

        storage_nodes = context.get_storage_nodes(path)

        # 在保存该对象的存储节点中，选择到候选节点方向带宽最小的路径作为保守估计。
        min_bw_storage = None
        min_bw = float('inf')
        for storage in storage_nodes:
            if storage == node.name:
                return 0

            bandwidth = context.get_dl_bandwidth(storage, node.name)
            if bandwidth < min_bw:
                min_bw = bandwidth
                min_bw_storage = storage

        if min_bw_storage:
            return int(data_item.size / min_bw)

        return 0

    def calculate_send_time(self, context: ClusterContext, pod: Pod, node: Node):
        """估算候选节点向存储节点写回输出对象所需时间。"""
        path = pod.spec.labels.get('data.skippy.io/sends-to-storage/path')

        if not path:
            return 0

        data_item = context.storage_index.stat(*path.split('/'))

        if not data_item:
            return 0

        storage_nodes = context.get_storage_nodes(path)

        # 在保存目标 bucket 的存储节点中，选择候选节点到存储节点方向带宽最小的路径作为保守估计。
        min_bw_storage = None
        min_bw = float('inf')
        for storage in storage_nodes:
            if storage == node.name:
                return 0

            bandwidth = context.get_dl_bandwidth(node.name, storage)
            if bandwidth < min_bw:
                min_bw = bandwidth
                min_bw_storage = storage

        if min_bw_storage:
            return int(data_item.size / min_bw)

        return 0

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """将传输时间代价反向缩放为优先级分数。"""
        return _scale_scores_inverse(node_scores, context.max_priority)
