"""
文件作用：faas-sim 与 Skippy 调度器的适配层，将 Ether 节点和 FunctionReplica 转换为调度器可识别的节点/Pod 视图。
主要类：SimulationClusterContext。
主要函数：to_skippy_node、create_function_pod。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""
import copy
import random
from collections import defaultdict
from typing import List, Dict

from ether.core import Node as EtherNode
from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Node as SkippyNode, Capacity as SkippyCapacity, ImageState, Pod, PodSpec, Container, \
    ResourceRequirements
from skippy.core.storage import StorageIndex
from skippy.core.utils import counter

from sim import docker
from sim.core import Environment
from sim.faas import FunctionContainer, FunctionDeployment
from sim.topology import LazyBandwidthGraph, DockerRegistry


class SimulationClusterContext(ClusterContext):

    """
    类作用：Skippy 调度上下文适配器，向调度器暴露节点、镜像缓存、存储节点和带宽图。
    继承关系：ClusterContext。
    核心方法：__init__、get_init_image_states、retrieve_image_state、get_bandwidth_graph、list_nodes、get_next_storage_node、storage_nodes、is_storage_node。
    """
    def __init__(self, env: Environment):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：_storage_nodes、bw_graph、container_registry、env、nodes、storage_index、topology。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env

        # 字段说明：self.topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
        self.topology = env.topology
        # 字段说明：self.container_registry：容器镜像仓库，保存可拉取镜像及其大小、架构信息。
        self.container_registry: docker.ContainerRegistry = env.container_registry
        # 字段说明：self.bw_graph：带宽图视图，供 Skippy 调度器评估节点间网络代价。
        self.bw_graph = None
        # 字段说明：self.nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。
        self.nodes = None

        super().__init__()

        # 字段说明：self.storage_index：存储节点索引，用于模拟函数输入/输出数据传输。
        self.storage_index = env.storage_index or StorageIndex()
        # 字段说明：self._storage_nodes：缓存后的存储节点列表，避免每次调度时重复遍历拓扑。
        self._storage_nodes = None

    def get_init_image_states(self) -> Dict[str, ImageState]:
        # 修正提示：这里标记了原实现中需要进一步确认的边界。
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return defaultdict(lambda: None)

    def retrieve_image_state(self, image_name: str) -> ImageState:
        # 修正提示：这里标记了原实现中需要进一步确认的边界。
        """
        函数作用：处理 retrieve、image、state 相关业务逻辑。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：image_name：表示 image、name，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        images = self.container_registry.find(image_name)

        if not images:
            raise ValueError('No container image "%s"' % image_name)

        if len(images) == 1 and images[0].arch is None:
            sizes = {
                'x86': images[0].size,
                'arm': images[0].size,
                'arm32v7': images[0].size,
                'aarch64': images[0].size,
                'arm64': images[0].size,
                'amd64': images[0].size
            }
        else:
            sizes = {image.arch: image.size for image in images if image.arch is not None}

        return ImageState(sizes)

    def get_bandwidth_graph(self):
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 写入对象字段：bw_graph。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if self.bw_graph is None:
            # 字段说明：self.bw_graph：带宽图视图，供 Skippy 调度器评估节点间网络代价。
            self.bw_graph = LazyBandwidthGraph(self.topology)

        return self.bw_graph

    def list_nodes(self) -> List[SkippyNode]:
        """
        函数作用：处理 list、nodes 相关业务逻辑。
        关键流程：
        - 写入对象字段：nodes。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if self.nodes is None:
            # 字段说明：self.nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。
            self.nodes = [to_skippy_node(node) for node in self.topology.get_nodes() if node != DockerRegistry]

        return self.nodes

    def get_next_storage_node(self, node: SkippyNode) -> str:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 使用随机采样生成设备属性、请求间隔或性能取值。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if self.is_storage_node(node):
            return node.name
        if not self.storage_nodes:
            return None

        bw = self.get_bandwidth_graph()[node.name]
        storage_nodes = list(self.storage_nodes.values())
        random.shuffle(storage_nodes)  
        storage_node = max(storage_nodes, key=lambda n: bw[n.name])

        return storage_node.name

    @property
    def storage_nodes(self) -> Dict[str, SkippyNode]:
        """
        函数作用：处理 storage、nodes 相关业务逻辑。
        关键流程：
        - 写入对象字段：_storage_nodes。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if self._storage_nodes is None:
            # 字段说明：self._storage_nodes：缓存后的存储节点列表，避免每次调度时重复遍历拓扑。
            self._storage_nodes = {node.name: node for node in self.list_nodes() if self.is_storage_node(node)}

        return self._storage_nodes

    def is_storage_node(self, node: SkippyNode):
        """
        函数作用：处理 is、storage、node 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return 'data.skippy.io/storage' in node.labels


def to_skippy_node(node: EtherNode) -> SkippyNode:
    """
    函数作用：将 Ether 节点转换为 Skippy 调度器使用的节点对象。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：node：候选或目标节点。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    capacity = SkippyCapacity(node.capacity.cpu_millis, node.capacity.memory)
    allocatable = copy.copy(capacity)

    labels = dict(node.labels)
    labels['beta.kubernetes.io/arch'] = node.arch

    return SkippyNode(node.name, capacity=capacity, allocatable=allocatable, labels=labels)


# 字段说明：pod_counters：表示 pod、counters，在当前业务流程中作为输入参数、状态字段或计算结果使用。
pod_counters = defaultdict(counter)


def create_function_pod(fd: 'FunctionDeployment', fn: 'FunctionContainer') -> Pod:
    """
    函数作用：根据函数副本创建 Skippy Pod 调度对象。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fd：函数部署对象，包含函数、容器规格和伸缩配置。；fn：函数定义对象或函数名。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    requests = fn.resource_config.get_resource_requirements()
    resource_requirements = ResourceRequirements(requests)

    spec = PodSpec()
    spec.containers = [Container(fn.image, resource_requirements)]
    spec.labels = fn.labels

    cnt = next(pod_counters[fd.name])
    pod = Pod(f'pod-{fd.name}-{cnt}', 'faas-sim')
    pod.spec = spec

    return pod
