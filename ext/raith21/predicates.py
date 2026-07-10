"""
Raith21 的 Skippy 调度谓词扩展。

本模块实现内存容量、可运行性、加速器匹配以及 GPU/TPU 独占约束，在优先级打分前过滤不合法节点。
"""

from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, Node
from skippy.core.predicates import Predicate

from ext.raith21.model import Accelerator
from sim.oracle.oracle import ResourceOracle, FetOracle


class HasEnoughRamPredicate(Predicate):
    """
    函数画像内存约束谓词。

    累加节点已有 Pod 的归一化 RAM 占用，并检查加入当前 Pod 后是否超过节点容量。

    关键字段:
        resource_oracle: 资源画像 Oracle。
    """
    def __init__(self, resource_oracle: ResourceOracle):
        """
        初始化 HasEnoughRamPredicate。

        建立字段：resource_oracle。

        参数:
            resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.resource_oracle = resource_oracle

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        检查加入当前 Pod 后，节点的归一化内存占用是否不超过 1。

        这里使用 ResourceOracle 的 ram 画像，而不是 Kubernetes resource requests；已有 Pod 和
        待调度 Pod 的 ram 值都按目标设备归一化后累加。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            bool。
        """
        host = node.name
        image = pod.spec.containers[0].image
        needed_ram = self.resource_oracle.get_resources(host, image)['ram']
        ram_in_use = 0
        # node.pods 是 Skippy 已经绑定到该节点的 Pod，包含正在启动和运行的副本。
        for running_pod in node.pods:
            running_image = running_pod.spec.containers[0].image
            ram_in_use += self.resource_oracle.get_resources(host, running_image)['ram']
        return ram_in_use + needed_ram <= 1


class CanRunPred(Predicate):
    """
    函数可运行性谓词。

    只有 FET Oracle 和 Resource Oracle 都包含目标节点/镜像组合时，节点才可进入打分阶段。

    关键字段:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 资源画像 Oracle。
    """
    def __init__(self, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        初始化 CanRunPred。

        建立字段：fet_oracle、resource_oracle。

        参数:
            fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
            resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.fet_oracle = fet_oracle
        self.resource_oracle = resource_oracle

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        检查目标设备类型是否同时具有该镜像的 FET 与资源画像。

        该谓词避免后续模拟器或优先级函数查询缺失画像；registry 永远不是计算节点。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            bool。
        """
        host = node.name[:node.name.rindex('_')] if '_' in node.name else node.name
        if host == 'registry':
            return False
        image = pod.spec.containers[0].image
        return self.fet_oracle.sample(host, image) is not None \
            and self.resource_oracle.get_resources(host, image) is not None


class NodeHasAcceleratorPred(Predicate):
    """
    加速器类型匹配谓词。

    当 Pod 声明 GPU/TPU 等加速器标签时，要求候选节点具有相同能力。
    """
    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        检查 Pod 声明的加速器类型是否与节点标签一致。

        未声明 device.edgerun.io/accelerator 的普通 Pod 不受该约束。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            bool。
        """
        accelerator_label = 'device.edgerun.io/accelerator'
        if accelerator_label in pod.spec.labels.keys():
            return pod.spec.labels[accelerator_label] == node.labels.get(accelerator_label, '')
        else:
            return True


class NodeHasFreeTpu(Predicate):
    """
    TPU 独占谓词。

    TPU 函数只能放到没有其他 TPU Pod 的节点，避免共享不支持并发隔离的设备。
    """
    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        对 TPU workload 实施节点级独占约束。

        如果候选节点已经放置另一个 TPU Pod，则当前 TPU Pod 被过滤；非 TPU Pod 直接通过。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            bool。
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
    GPU 可用性谓词。

    可选择 GPU 独占模式，或按 Pod 声明的显存需求检查节点剩余 VRAM。

    关键字段:
        use_vram: 是否按显存容量而不是独占方式判断 GPU 可用性。
    """
    def __init__(self, use_vram: bool = False):
        """
        初始化 NodeHasFreeGpu。

        建立字段：use_vram。

        参数:
            use_vram: 是否按显存容量共享 GPU。 类型：bool。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.use_vram = use_vram

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        """
        检查 GPU 是否可供当前 Pod 使用。

        use_vram=False 时一块 GPU 只允许一个 GPU Pod；use_vram=True 时累计已有 Pod 的
        device.edgerun.io/vram 请求，并与节点显存容量比较。

        参数:
            context: Skippy 集群上下文。 类型：ClusterContext。
            pod: 待调度 Pod。 类型：Pod。
            node: 候选 Skippy 节点。 类型：Node。

        返回:
            bool。
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
