"""
文件作用：Skippy 调度谓词扩展，判断节点是否满足内存、架构、加速器、TPU/GPU 独占等硬约束。
主要类：HasEnoughRamPredicate、CanRunPred、NodeHasAcceleratorPred、NodeHasFreeTpu、NodeHasFreeGpu。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node
from skippy.core.predicates import Predicate

from ext.raith21.model import Accelerator
from sim.oracle.oracle import ResourceOracle, FetOracle


class HasEnoughRamPredicate(Predicate):
    """
    类作用：内存容量谓词，过滤可用内存不足以承载函数资源请求的节点。
    继承关系：Predicate。
    核心方法：__init__、passes_predicate。
    """
    def __init__(self, resource_oracle: ResourceOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：resource_oracle。
        参数：resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
        self.resource_oracle = resource_oracle

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        函数作用：判断候选节点是否满足调度硬约束。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        host = node.name
        image = pod.spec.containers[0].image
        needed_ram = self.resource_oracle.get_resources(host, image)['ram']
        ram_in_use = 0
        for running_pod in node.pods:
            running_image = running_pod.spec.containers[0].image
            ram_in_use += self.resource_oracle.get_resources(host, running_image)['ram']
        return ram_in_use + needed_ram <= 1


class CanRunPred(Predicate):
    """
    类作用：架构/镜像可运行谓词，判断节点是否能够运行该函数容器镜像。
    继承关系：Predicate。
    核心方法：__init__、passes_predicate。
    """
    def __init__(self, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fet_oracle、resource_oracle。
        参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。
        self.fet_oracle = fet_oracle
        # 字段说明：self.resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
        self.resource_oracle = resource_oracle

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        函数作用：判断候选节点是否满足调度硬约束。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        host = node.name[:node.name.rindex('_')] if '_' in node.name else node.name
        if host == 'registry':
            return False
        image = pod.spec.containers[0].image
        return self.fet_oracle.sample(host, image) is not None \
            and self.resource_oracle.get_resources(host, image) is not None


class NodeHasAcceleratorPred(Predicate):
    """
    类作用：加速器谓词，检查函数需求中的 GPU/TPU 等能力是否被节点满足。
    继承关系：Predicate。
    核心方法：passes_predicate。
    """
    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        函数作用：判断候选节点是否满足调度硬约束。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        accelerator_label = 'device.edgerun.io/accelerator'
        if accelerator_label in pod.spec.labels.keys():
            return pod.spec.labels[accelerator_label] == node.labels.get(accelerator_label, '')
        else:
            return True


class NodeHasFreeTpu(Predicate):
    """
    类作用：TPU 独占谓词，避免多个函数同时抢占同一节点的 TPU。
    继承关系：Predicate。
    核心方法：passes_predicate。
    """
    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        函数作用：判断候选节点是否满足调度硬约束。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        accelerator_label = 'device.edgerun.io/accelerator'
        if pod.spec.labels.get(accelerator_label, '') == str(Accelerator.TPU.name):
            for running_pod in node.pods:
                if running_pod.spec.labels.get(accelerator_label, '') == 'TPU':
                    return False

            return True
        else:
            return True


class NodeHasFreeGpu(Predicate):

    """
    类作用：GPU 独占谓词，避免 GPU 资源被不兼容的函数副本重复占用。
    继承关系：Predicate。
    核心方法：__init__、passes_predicate。
    """
    def __init__(self, use_vram: bool = False):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：use_vram。
        参数：use_vram：是否将 GPU 显存作为调度和资源建模因素。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.use_vram：是否将 GPU 显存作为调度和资源建模因素。
        self.use_vram = use_vram

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        函数作用：判断候选节点是否满足调度硬约束。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        accelerator_label = 'device.edgerun.io/accelerator'
        vram_label = 'device.edgerun.io/vram'
        if pod.spec.labels.get(accelerator_label, '') == str(Accelerator.GPU.name):
            if not self.use_vram:
                for running_pod in node.pods:
                    if running_pod.spec.labels.get(accelerator_label, '') == str(Accelerator.GPU.name):
                        return False
                return True

            vram_needed = int(pod.spec.labels[vram_label])
            vram_size = int(node.labels[vram_label])
            reserved_vram = 0
            for running_pod in node.pods:
                if running_pod.spec.labels.get(accelerator_label, '') == str(Accelerator.GPU.name):
                    reserved_vram += int(running_pod.spec.labels.get(vram_label, '0'))

            return vram_needed + reserved_vram <= vram_size
        else:
            return True
