"""
文件作用：Skippy 调度优先级扩展，根据能力匹配、预计执行时间和资源竞争情况为候选节点打分。
主要类：CapabilityMatchingPriority、ExecutionTimePriority、ContentionPriority。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

import ast
from typing import Dict

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node
from skippy.core.priorities import Priority, _scale_scores

from sim.oracle.oracle import FetOracle, ResourceOracle


class CapabilityMatchingPriority(Priority):
    """
    类作用：能力匹配优先级，越满足函数硬件/位置/资源需求的节点得分越高。
    继承关系：Priority。
    核心方法：map_node_score、reduce_mapped_score。
    """
    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        函数作用：为单个候选节点计算调度优先级分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        priority = 0
        raw_requirements = pod.spec.labels.get('device.edgerun.io/requirements', None)
        if raw_requirements is None:
            return 0

        node_caps = dict(filter(lambda label: 'device.edgerun.io' in label[0], node.labels.items()))

        requirements: Dict[str, Dict[str, float]] = ast.literal_eval(raw_requirements)
        for capability in node_caps.items():
            label = requirements.get(capability[0], None)
            if label is not None:
                priority += label.get(capability[1], 0)

        return priority

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """
        函数作用：把节点原始分数归一化为调度器使用的最终分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；node_scores：候选节点分数集合，用于调度优先级归一化和最终排序。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return _scale_scores(node_scores, context.max_priority)


class ExecutionTimePriority(Priority):

    """
    类作用：执行时间优先级，利用 FET Oracle 预测候选节点执行速度并转换为调度分数。
    继承关系：Priority。
    核心方法：__init__、map_node_score、reduce_mapped_score。
    """
    def __init__(self, fet_oracle: FetOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fet_oracle。
        参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。
        self.fet_oracle = fet_oracle

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        函数作用：为单个候选节点计算调度优先级分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        fet = self.fet_oracle.sample(node.name, pod.spec.containers[0].image)
        return -fet if fet is not None else 0

    def reduce_mapped_score(self, context: ClusterContext, pod: Pod, nodes: [Node], node_scores: [int]) -> [int]:
        """
        函数作用：把节点原始分数归一化为调度器使用的最终分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；node_scores：候选节点分数集合，用于调度优先级归一化和最终排序。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return _scale_scores(node_scores, context.max_priority)


class ContentionPriority(Priority):

    """
    类作用：资源竞争优先级，根据磁盘、网络和已有负载估计节点竞争风险并打分。
    继承关系：Priority。
    核心方法：__init__、_get_disk_speed、_get_net_speed、map_node_score、reduce_mapped_score。
    """
    def __init__(self, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fet_oracle、resource_oracle。
        参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。
        self.fet_oracle = fet_oracle
        # 字段说明：self.resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
        self.resource_oracle = resource_oracle

    def _get_disk_speed(self, disk: str):
        """
        函数作用：处理 get、disk、speed 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：disk：存储介质类型。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        """
        函数作用：处理 get、net、speed 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：location：设备所处层级，例如云、边缘、MEC 或移动端。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if 'CLOUD' in location:
            return 1000e6
        else:
            return 125e6

    def map_node_score(self, context: ClusterContext, pod: Pod, node: Node) -> int:
        """
        函数作用：为单个候选节点计算调度优先级分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        image = pod.spec.containers[0].image
        host = node.name[:node.name.rindex('_')]
        usage = self.resource_oracle.get_resources(host, image)
        
        pod_blkio = usage['blkio']
        pod_net = usage['net']
        pod_cpu = usage['cpu']
        pod_gpu = usage['gpu']

        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        running_cpu = 0
        running_blkio = 0
        running_net = 0
        running_gpu = 0
        counter = 0
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
        函数作用：把节点原始分数归一化为调度器使用的最终分数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；node_scores：候选节点分数集合，用于调度优先级归一化和最终排序。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return _scale_scores(node_scores, context.max_priority)
