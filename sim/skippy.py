"""
Skippy 调度器适配层。

本模块把 faas-sim 的 Ether 节点、函数部署和副本对象转换为 Skippy 调度器理解的 Node 与 Pod 视图，并提供调度上下文所需的镜像、带宽和存储节点查询接口。

阅读建议：重点看 Ether/Function 对象如何转换成 Skippy Node/Pod。
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
    Skippy 调度上下文适配器。

    向 Skippy 暴露节点、镜像缓存、带宽图、存储节点和资源状态等信息。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - topology: Ether 拓扑对象，描述节点、链路和路由关系。
    - container_registry: 容器镜像仓库，按镜像名、tag 和架构保存镜像大小等元数据。
    - bw_graph: 延迟带宽图，按需查询节点间带宽。
    - nodes: Skippy 节点列表缓存。
    - storage_index: Skippy 存储索引，用于描述数据所在节点。
    - _storage_nodes: 缓存后的存储节点索引。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, env: Environment):
        """
        初始化 SimulationClusterContext 对象。

        主要建立字段：env、topology、container_registry、bw_graph、nodes、storage_index、_storage_nodes。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env

        self.topology = env.topology
        self.container_registry: docker.ContainerRegistry = env.container_registry
        self.bw_graph = None
        self.nodes = None

        super().__init__()

        self.storage_index = env.storage_index or StorageIndex()
        self._storage_nodes = None

    def get_init_image_states(self) -> Dict[str, ImageState]:
        """
        返回 Skippy 初始化镜像状态表。

        当前实现返回默认空状态，实际镜像可用性由容器仓库和节点 NodeState 中的 docker_images 在运行时共同决定。

        返回说明：返回值类型标注为 Dict[str, ImageState]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return defaultdict(lambda: None)

    def retrieve_image_state(self, image_name: str) -> ImageState:
        """
        从容器仓库构造 Skippy 需要的 ImageState。

        如果镜像没有声明架构，则把同一大小复制到常见架构；如果声明了架构，则按 arch -> size 组织，供调度器判断镜像兼容性和拉取成本。

        参数说明：
        - image_name: 镜像字符串，用于从容器仓库构造 ImageState。 类型标注：str。

        返回说明：返回值类型标注为 ImageState，通常作为后续调度、执行、统计或查询流程的输入。
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
        返回延迟初始化的带宽图。

        第一次调用时创建 LazyBandwidthGraph，后续复用同一个对象，以便缓存已经查询过的链路带宽。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        if self.bw_graph is None:
            self.bw_graph = LazyBandwidthGraph(self.topology)

        return self.bw_graph

    def list_nodes(self) -> List[SkippyNode]:
        """
        返回 Skippy 视角下的集群节点列表。

        方法会把 Ether 节点转换为 Skippy Node，并排除 Docker registry 节点，因为 registry 只参与镜像传输，不参与函数调度。

        返回说明：返回值类型标注为 List[SkippyNode]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        if self.nodes is None:
            self.nodes = [to_skippy_node(node) for node in self.topology.get_nodes() if node != DockerRegistry]

        return self.nodes

    def get_next_storage_node(self, node: SkippyNode) -> str:
        """
        选择距离给定节点最近的存储节点。

        如果节点本身就是存储节点则直接返回；否则在所有存储节点中按带宽最大原则选择一个，带宽并列时通过随机打乱降低固定偏置。

        参数说明：
        - node: 目标节点或节点视图。 类型标注：SkippyNode。

        返回说明：返回值类型标注为 str，通常作为后续调度、执行、统计或查询流程的输入。
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
        返回带有 data.skippy.io/storage 标签的节点索引。

        结果按节点名缓存，供数据下载、上传和调度 Oracle 查找存储位置。

        返回说明：返回值类型标注为 Dict[str, SkippyNode]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        if self._storage_nodes is None:
            self._storage_nodes = {node.name: node for node in self.list_nodes() if self.is_storage_node(node)}

        return self._storage_nodes

    def is_storage_node(self, node: SkippyNode):
        """
        判断 Skippy 节点是否是存储节点。

        判断依据是节点 labels 中是否包含 data.skippy.io/storage。

        参数说明：
        - node: 目标节点或节点视图。 类型标注：SkippyNode。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return 'data.skippy.io/storage' in node.labels


def to_skippy_node(node: EtherNode) -> SkippyNode:
    """
    把 Ether 节点转换成 Skippy 调度器节点。

    转换时复制容量为 capacity/allocatable，并把 Ether 节点架构写入 beta.kubernetes.io/arch 标签，供镜像架构匹配使用。

    参数说明：
    - node: 目标节点或节点视图。 类型标注：EtherNode。

    返回说明：返回值类型标注为 SkippyNode，通常作为后续调度、执行、统计或查询流程的输入。
    """
    capacity = SkippyCapacity(node.capacity.cpu_millis, node.capacity.memory)
    allocatable = copy.copy(capacity)

    labels = dict(node.labels)
    labels['beta.kubernetes.io/arch'] = node.arch

    return SkippyNode(node.name, capacity=capacity, allocatable=allocatable, labels=labels)


pod_counters = defaultdict(counter)


def create_function_pod(fd: 'FunctionDeployment', fn: 'FunctionContainer') -> Pod:
    """
    根据函数部署和容器规格创建 Skippy Pod。

    Pod 中包含一个 Container、资源请求、函数标签以及稳定递增的 pod 名称，后续会交给调度器选择运行节点。

    参数说明：
    - fd: FunctionDeployment，描述一个函数的定义、容器、伸缩配置和镜像排序。 类型标注：'FunctionDeployment'。
    - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：'FunctionContainer'。

    返回说明：返回值类型标注为 Pod，通常作为后续调度、执行、统计或查询流程的输入。
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
