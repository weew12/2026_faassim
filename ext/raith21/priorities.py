"""
Raith21 的 workload-aware 调度优先级。

本模块根据设备能力匹配、预计函数执行时间和同节点资源争用为可行节点打分，是论文调度策略的核心实现。
"""

import ast
from typing import Dict

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node
from skippy.core.priorities import Priority, _scale_scores

from sim.oracle.oracle import FetOracle, ResourceOracle


class CapabilityMatchingPriority(Priority):
    """
    设备能力匹配优先级。

    比较 Pod 需求标签与节点能力标签，匹配项越多得分越高。
    """
    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        累加节点能力与 Pod 概率需求的匹配权重。

        Pod 的 device.edgerun.io/requirements 标签保存 Requirements.to_dict() 的字符串形式；
        节点每匹配一个属性取值，就累加该取值在需求分布中的概率。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            int。
        """
        priority = 0
        raw_requirements = pod.spec.labels.get('device.edgerun.io/requirements', None)
        if raw_requirements is None:
            return 0

        # 只比较 Raith21 设备标签，忽略 Kubernetes/Skippy 的其他控制标签。
        node_caps = dict(filter(lambda label: 'device.edgerun.io' in label[0], node.labels.items()))

        requirements: Dict[str, Dict[str, float]] = ast.literal_eval(raw_requirements)
        for capability in node_caps.items():
            label = requirements.get(capability[0], None)
            if label is not None:
                priority += label.get(capability[1], 0)

        return priority

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """
        把全部候选节点的原始值归一化为 Skippy 优先级分数。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            nodes: Ether 或 Skippy 节点集合。 类型：[Node]。
            node_scores: 全部候选节点的原始分数列表。 类型：[int]。

        返回:
            [int]。
        """
        return _scale_scores(node_scores, context.max_priority)


class ExecutionTimePriority(Priority):

    """
    预计执行时间优先级。

    通过 FET Oracle 估计 Pod 在各节点上的执行时间，并反向缩放，使更快节点获得更高分。

    关键字段:
        fet_oracle: 函数执行时间 Oracle。
    """
    def __init__(self, fet_oracle: FetOracle):
        """
        初始化 ExecutionTimePriority。

        建立字段：fet_oracle。

        参数:
            fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        super().__init__()
        self.fet_oracle = fet_oracle

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        返回候选节点上预计 FET 的负值。

        _scale_scores 按数值从小到大缩放，因此先取负数可让执行时间更短的节点获得高分。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            int。
        """
        fet = self.fet_oracle.sample(node.name, pod.spec.containers[0].image)
        return -fet if fet is not None else 0

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """
        把全部候选节点的原始值归一化为 Skippy 优先级分数。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            nodes: Ether 或 Skippy 节点集合。 类型：[Node]。
            node_scores: 全部候选节点的原始分数列表。 类型：[int]。

        返回:
            [int]。
        """
        return _scale_scores(node_scores, context.max_priority)


class ContentionPriority(Priority):

    """
    资源争用优先级。

    根据候选节点现有 Pod 的资源画像、节点磁盘和网络能力估计潜在竞争，争用越低得分越高。

    关键字段:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 资源画像 Oracle。
    """
    def __init__(self, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        初始化 ContentionPriority。

        建立字段：fet_oracle、resource_oracle。

        参数:
            fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
            resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        super().__init__()
        self.fet_oracle = fet_oracle
        self.resource_oracle = resource_oracle

    def _get_disk_speed(self, disk: str):
        """
        把磁盘类型标签映射为近似顺序吞吐率，单位为字节/秒。

        参数:
            disk: 节点磁盘类型标签。 类型：str。

        返回:
            计算、查询或构造得到的结果。
        """
        if 'NVME' in disk:
            return 2500e6
        if 'SSD' in disk:
            return 500e6
        if 'HDD' in disk:
            return 250e6
        if 'FLASH' in disk:
            return 150e6
        if 'SD' in disk:
            return 50e6

        return 1

    def _get_net_speed(self, location: str):
        """
        按云端/边缘位置返回归一化网络吞吐率，单位为字节/秒。

        参数:
            location: 节点位置类型标签。 类型：str。

        返回:
            计算、查询或构造得到的结果。
        """
        if 'CLOUD' in location:
            return 1000e6
        else:
            return 125e6

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        估计把 Pod 加入候选节点后的相对资源争用得分。

        CPU/GPU 画像直接使用归一化占用；网络和块 I/O 会除以节点近似吞吐能力。
        当前 Pod 需求减去已有 Pod 总占用，空闲程度更高的节点通常得到更大的原始值。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            int。
        """
        image = pod.spec.containers[0].image
        host = node.name[:node.name.rindex('_')]
        usage = self.resource_oracle.get_resources(host, image)
        
        pod_blkio = usage['blkio']
        pod_net = usage['net']
        pod_cpu = usage['cpu']
        pod_gpu = usage['gpu']

        running_cpu = 0
        running_blkio = 0
        running_net = 0
        running_gpu = 0
        counter = 0
        # 汇总节点上已经放置的 Pod 资源画像，近似表达共享 CPU、GPU、磁盘和网络的压力。
        for running_pod in node.pods:
            image = running_pod.spec.containers[0].image
            usage = self.resource_oracle.get_resources(host, image)
            if usage != None:
                running_blkio += usage['blkio']
                running_net += usage['net']
                running_cpu += usage['cpu']
                running_gpu += usage['gpu']
                counter += 1
        if counter > 0:
            # 网络与块 I/O 原始画像除以设备吞吐率后，才能与 CPU/GPU 占用共同比较。
            running_net /= self._get_net_speed(node.labels.get('device.edgerun.io/location'))
            running_blkio /= self._get_disk_speed(node.labels.get('device.edgerun.io/disk'))

        pod_net /= self._get_net_speed(node.labels.get('device.edgerun.io/location'))
        pod_blkio /= self._get_disk_speed(node.labels.get('device.edgerun.io/disk'))

        
        pod_usage = (pod_blkio + pod_net + pod_cpu + pod_gpu)
        running_usage = (running_blkio + running_net + running_gpu + running_cpu)
        priority = pod_usage - running_usage
        return priority

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """
        把全部候选节点的原始值归一化为 Skippy 优先级分数。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            nodes: Ether 或 Skippy 节点集合。 类型：[Node]。
            node_scores: 全部候选节点的原始分数列表。 类型：[int]。

        返回:
            [int]。
        """
        return _scale_scores(node_scores, context.max_priority)
