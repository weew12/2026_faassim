"""Skippy 调度领域模型。

本文件定义调度器运行所需的最小 Kubernetes 风格对象模型。它不直接依赖 Kubernetes
API，而是用纯 Python 对象表达调度决策中需要的关键状态：节点容量、节点剩余资源、
Pod 内容器镜像、容器资源请求、Pod 标签和调度结果。

在 faas-sim 中，``sim/skippy.py`` 会把函数部署转换为 ``Pod``，把 Ether 节点转换为
``Node``。随后 ``Scheduler.schedule`` 基于这些对象执行谓词过滤和优先级打分。
"""

from typing import Dict, List, NamedTuple


class ImageState:
    """    容器镜像在调度器视角下的运行态元数据。

    业务作用：
    - 记录同一个逻辑镜像在不同 CPU 架构下的镜像大小；
    - 记录该镜像当前已经分布在多少个节点上；
    - 支撑镜像本地性优先级函数判断“把 Pod 放到某节点后是否需要额外拉镜像”。

    字段：
    - ``size``：键为节点架构，例如 ``amd64``、``arm32v7``、``aarch64``，值为该架构镜像大小，单位为字节；
    - ``num_nodes``：当前已缓存该镜像的节点数量，用于衡量镜像在集群中的扩散程度。
    """

    # 不同 CPU 架构对应的镜像大小，单位为字节。
    size: Dict[str, int]
    # 当前缓存该镜像的节点数量。
    num_nodes: int = 0

    def __init__(self, size: Dict[str, int], num_nodes: int = 0):
        """初始化镜像状态。"""
        # 保存多架构镜像大小表，调度器会按目标节点架构读取对应大小。
        self.size = size
        # 保存镜像已出现的节点数量，节点第一次放置该镜像时会递增。
        self.num_nodes = num_nodes

    def __str__(self) -> str:
        """返回便于日志输出的镜像状态字符串。"""
        return "ImageState%s" % self.__dict__

    def __repr__(self):
        """交互式调试时复用 ``__str__`` 输出。"""
        return self.__str__()


class ResourceRequirements:
    """    容器资源请求描述。

    业务作用：
    该对象模拟 Kubernetes ``resources.requests`` 的核心语义。Skippy 调度器只关心
    调度前的资源占位，因此这里主要记录 CPU 与内存请求量，并在资源谓词和资源均衡
    优先级函数中使用。

    默认值沿用 Kubernetes 调度器中非零资源请求的思想：若用户没有显式声明请求量，
    调度器仍按一个较小的默认资源占位进行计算，避免完全零请求导致资源评分失真。
    """

    # 默认 CPU 请求，单位为 millicore；100 表示 0.1 个 CPU 核。
    default_milli_cpu_request = 100
    # 默认内存请求，单位为字节；此处为 200 MB。
    default_mem_request = 200 * 1024 * 1024
    # 默认资源请求字典，供未显式设置资源请求的容器复用。
    default_requests: Dict[str, float] = {"cpu": default_milli_cpu_request, "memory": default_mem_request}

    def __init__(self, requests: Dict[str, float] = None) -> None:
        """        创建资源请求对象。

        参数：
        - ``requests``：资源请求字典，常用键为 ``cpu`` 和 ``memory``；若为空则使用默认请求量。
        """
        super().__init__()
        # 复制默认字典，避免多个 ResourceRequirements 共享同一个可变 dict。
        self.requests = requests or dict(ResourceRequirements.default_requests)


class Container:
    """    Pod 内的容器描述。

    业务作用：
    调度器并不真正启动容器，而是使用该对象表达“这个 Pod 需要哪些镜像以及每个镜像
    需要占用多少资源”。在 faas-sim 中，一个函数副本通常会被转换为包含一个容器的
    Pod；该容器的 ``image`` 对应函数镜像，``resources`` 对应函数容器资源需求。
    """

    # 容器资源请求对象，包含 CPU 与内存请求。
    resources: ResourceRequirements = ResourceRequirements()
    # 容器镜像名，可能是不带 tag 的名称，调度时会通过 normalize_image_name 规范化。
    image: str

    def __init__(self, image: str, resources: ResourceRequirements = None) -> None:
        """初始化容器描述。"""
        super().__init__()
        # 资源请求为空时使用默认请求量，保证资源谓词始终有可计算输入。
        self.resources = resources or ResourceRequirements()
        # 保存容器镜像名，后续镜像本地性和镜像拉取模拟都会读取该字段。
        self.image = image


class PodSpec:
    """    Pod 规格描述。

    业务作用：
    该对象聚合 Pod 的容器列表和标签集合。容器列表决定资源占用与镜像需求，标签集合
    则承载数据本地性、能力需求、存储读写路径等调度信息。例如 faas-sim 的 raith21
    实验扩展会在标签中写入 ``data.skippy.io/receives-from-storage/path``，供数据本地性
    优先级函数计算数据传输代价。
    """

    # Pod 内部容器列表，Skippy 会逐个累加资源请求和镜像大小。
    containers: List[Container]
    # Pod 标签字典，用于表达数据输入输出、硬件能力需求等调度约束或偏好。
    labels: Dict[str, str]

    def __init__(self, containers: List[Container] = None, labels: Dict[str, str] = None) -> None:
        """初始化 PodSpec，确保容器列表和标签字典均为独立对象。"""
        super().__init__()
        if containers is None:
            containers = []
        if labels is None:
            labels = {}
        # 保存待调度 Pod 的容器集合。
        self.containers = containers
        # 保存待调度 Pod 的标签集合。
        self.labels = labels


class Pod:
    """    调度器视角下的 Pod。

    业务作用：
    Pod 是 Skippy 调度的基本单位。faas-sim 每创建一个函数副本，就会构造一个对应的
    Pod 对象交给调度器。调度结果中的 suggested_host 表示这个 Pod 应当放置到哪个节点。
    """

    # Pod 名称，faas-sim 通常用函数副本名称或生成序号构造。
    name: str
    # 命名空间名称，用于保留 Kubernetes 风格对象结构。
    namespace: str
    # Pod 规格，包含容器列表和调度标签。
    spec: PodSpec

    def __init__(self, name: str, namespace: str, spec: PodSpec = None) -> None:
        """初始化 Pod 对象。"""
        super().__init__()
        # 保存 Pod 名称，日志和调度跟踪会使用该值。
        self.name = name
        # 保存命名空间，便于与 Kubernetes/OpenFaaS 的部署语义对齐。
        self.namespace = namespace
        # 保存 PodSpec；调用方应保证该字段不为空。
        self.spec = spec


class Capacity:
    """    节点容量或剩余可分配资源。

    业务作用：
    该对象既可表示节点总容量 ``capacity``，也可表示节点当前剩余可分配资源
    ``allocatable``。Skippy 在放置 Pod 时会减少 ``allocatable``，在移除 Pod 时会恢复。
    """

    def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1024 * 1024 * 1024):
        """        初始化资源容量。

        参数：
        - ``cpu_millis``：CPU 容量，单位为 millicore；1000 表示 1 个核心；
        - ``memory``：内存容量，单位为字节。
        """
        # 节点内存容量或剩余内存，单位为字节。
        self.memory = memory
        # 节点 CPU 容量或剩余 CPU，单位为 millicore。
        self.cpu_millis = cpu_millis

    def __str__(self):
        """返回可读的容量字符串，便于日志观察调度后剩余资源。"""
        return 'Capacity(CPU: {0} Memory: {1})'.format(self.cpu_millis, self.memory)


class Node:
    """    调度器视角下的计算节点。

    业务作用：
    Node 表示 Kubernetes Worker/边缘节点在调度器中的简化模型。它保存节点总容量、
    剩余资源、标签和已放置 Pod。标签用于表达架构、边缘/云位置、GPU/TPU 等能力；
    剩余资源用于资源过滤和资源均衡评分。
    """

    # 节点名称，需要与 faas-sim/Ether 节点名称保持一致，便于跨模块关联。
    name: str
    # 已经被调度到该节点的 Pod 列表。
    pods: List[Pod]
    # 节点总资源容量。
    capacity: Capacity
    # 节点剩余可分配资源；该字段是运行态，会随 Pod 放置和移除动态变化。
    allocatable: Capacity
    # 节点标签，表达架构、位置、能力和存储角色等调度信息。
    labels: Dict[str, str]

    def __init__(self, name: str, capacity: Capacity = None, allocatable: Capacity = None,
                 labels: Dict[str, str] = None) -> None:
        """初始化节点对象。"""
        super().__init__()
        # 保存节点名称。
        self.name = name
        # 保存节点总容量；未指定时使用 1 核/1GB 的默认容量。
        self.capacity = capacity or Capacity()
        # 保存节点剩余可分配资源；未指定时同样使用默认容量。
        self.allocatable = allocatable or Capacity()
        # 保存节点标签；调度谓词和优先级函数会读取该字段。
        self.labels = labels or {}
        # 保存已经放置在该节点上的 Pod，用于恢复资源和观察节点状态。
        self.pods = list()

    def __repr__(self):
        """调试输出时直接显示节点名称。"""
        return self.name


class SchedulingResult(NamedTuple):
    """    调度结果。

    字段：
    - ``suggested_host``：最终建议放置 Pod 的节点；若没有可行节点则为 ``None``；
    - ``feasible_nodes``：经过谓词过滤后参与打分的可行节点数量；
    - ``needed_images``：目标节点尚未缓存、需要在部署阶段拉取的镜像名列表。
    """

    suggested_host: Node
    feasible_nodes: int
    needed_images: List[str]
