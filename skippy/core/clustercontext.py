"""Skippy 集群上下文抽象。

该文件定义调度器读取和更新集群运行态的统一接口。对应到 Kubernetes，可以把它理解为
调度器通过 API Server/etcd 看到的集群快照；对应到 faas-sim，它由 ``SimulationClusterContext``
实现，并把 Ether 拓扑、函数镜像仓库、对象存储索引和节点剩余资源暴露给 Skippy。

ClusterContext 既是只读查询入口，也是调度后的状态更新入口：调度器选中节点后，会通过
``place_pod_on_node`` 扣减节点可分配资源并登记镜像缓存状态；函数副本释放时，则通过
``remove_pod_from_node`` 恢复资源。
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import List, Dict

from skippy.core.model import Node, Pod, ImageState
from skippy.core.storage import StorageIndex
from skippy.core.utils import normalize_image_name

# 带宽图类型：bandwidth[from_node][to_node] = 从 from_node 到 to_node 的可用带宽，单位为字节/秒。
BandwidthGraph = Dict[str, Dict[str, float]]


class ClusterContext(ABC):
    """    集群运行态上下文基类。

    业务职责：
    - 提供调度器所需的节点列表、镜像元数据、带宽图和存储索引；
    - 维护镜像在节点上的缓存分布，支撑镜像本地性评分；
    - 维护节点剩余 CPU/内存，支撑资源过滤和调度后状态更新；
    - 为数据本地性评分提供对象存储节点查询能力。
    """

    def __init__(self):
        """初始化集群上下文运行态字段。"""
        # 镜像元数据表，键为规范化镜像名，值为 ImageState。
        self.image_states: Dict[str, ImageState] = self.get_init_image_states()

        # 单个优先级函数的最高分值，默认与 Kubernetes 调度打分范围保持一致。
        self.max_priority: int = 10

        # 节点本地镜像缓存表：images_on_nodes[node_name][image_name] = ImageState。
        self.images_on_nodes: Dict[str, Dict[str, ImageState]] = defaultdict(dict)

        # 节点间带宽图，用于镜像拉取时间和数据传输时间估算。
        self.bandwidth: BandwidthGraph = self.get_bandwidth_graph()

        # 对象存储索引，由 faas-sim benchmark 或拓扑初始化阶段注入。
        self.storage_index: StorageIndex = None

    def get_node(self, name: str) -> Node:
        """按节点名称查找 Skippy 节点对象；未找到时返回 ``None``。"""
        for node in self.list_nodes():
            if node.name == name:
                return node

    @abstractmethod
    def get_init_image_states(self) -> Dict[str, ImageState]:
        """返回仿真开始时已知的镜像元数据表。"""
        raise NotImplemented()

    @abstractmethod
    def get_bandwidth_graph(self) -> Dict[str, Dict[str, float]]:
        """返回节点间带宽图。"""
        raise NotImplemented()

    @abstractmethod
    def list_nodes(self) -> List[Node]:
        """返回可参与调度的节点列表。"""
        raise NotImplemented()

    @abstractmethod
    def get_next_storage_node(self, node: Node) -> str:
        """根据当前节点选择一个可用存储节点，具体策略由子类实现。"""
        raise NotImplemented()

    def get_storage_nodes(self, urn: str) -> List[str]:
        """        返回保存指定对象的存储节点列表。

        参数：
        - ``urn``：对象路径，当前使用 ``bucket/object`` 形式。

        返回：
        - 保存该 bucket 的节点名称列表。当前实现假定同一 bucket 内对象位于 bucket 节点上。
        """
        # 当前实现采用简单的 bucket/object 路径，尚未引入更复杂的对象寻址协议。
        bucket, name = urn.split('/')
        # 当前存储模型假设每个 bucket 的对象可从该 bucket 的存储节点读取。
        return [name for name in self.storage_index.get_bucket_nodes(bucket)]

    def place_pod_on_node(self, pod: Pod, node: Node):
        """        将 Pod 登记到节点上，并更新调度器运行态。

        关键流程：
        1. 遍历 Pod 中的容器，规范化镜像名；
        2. 如果目标节点尚未缓存该镜像，则登记镜像并增加镜像分布计数；
        3. 按容器资源请求扣减节点剩余 CPU 和内存；
        4. 将 Pod 加入节点的已放置 Pod 列表。

        注意：这里更新的是调度器内部状态，不代表真实容器已经启动。faas-sim 后续还会模拟
        镜像拉取、容器启动、setup 和请求执行等生命周期阶段。
        """
        for container in pod.spec.containers:
            image_name = normalize_image_name(container.image)

            if image_name not in self.images_on_nodes[node.name]:
                image_state = self.get_image_state(image_name)

                # 镜像首次出现在该节点，镜像分布节点数加一。
                image_state.num_nodes += 1

                # 将镜像状态写入该节点的本地镜像缓存表。
                images_on_nodes = self.images_on_nodes[node.name]
                images_on_nodes[image_name] = image_state
                self.images_on_nodes[node.name][image_name] = image_state

            # 提取容器资源请求；未声明时使用默认请求量。
            required_cpu_millis = container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
            required_memory = container.resources.requests.get('memory', container.resources.default_mem_request)

            # 扣减节点剩余可分配资源，影响后续 Pod 的资源过滤和评分。
            node.allocatable.cpu_millis -= required_cpu_millis
            node.allocatable.memory -= required_memory
        # 登记 Pod 与节点的放置关系。
        node.pods.append(pod)

    def remove_pod_from_node(self, pod: Pod, node: Node):
        """        从节点上移除 Pod，并恢复其占用的 CPU/内存资源。

        该方法用于函数副本缩容或释放时的调度状态回滚。镜像缓存不会在这里删除，因为
        容器退出后镜像通常仍可留在节点本地；如果需要同步删除镜像缓存，应调用
        ``remove_pod_images_from_node``。
        """
        for container in pod.spec.containers:
            required_cpu_millis = container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
            required_memory = container.resources.requests.get('memory', container.resources.default_mem_request)

            # 恢复节点剩余可分配资源。
            node.allocatable.cpu_millis += required_cpu_millis
            node.allocatable.memory += required_memory
        node.pods.remove(pod)

    def remove_pod_images_from_node(self, pod: Pod, node: Node):
        """        从节点镜像缓存表中移除 Pod 使用的镜像。

        业务语义：
        默认缩容只释放运行资源，不一定删除本地镜像。本方法用于显式模拟镜像缓存清理或
        节点状态重置，调用后会降低镜像分布计数，从而影响后续镜像本地性评分。
        """
        for container in pod.spec.containers:
            image_name = normalize_image_name(container.image)

            if image_name in self.images_on_nodes[node.name]:
                image_state = self.get_image_state(image_name)
                image_state.num_nodes -= 1
                del self.images_on_nodes[node.name][image_name]

    def get_image_state(self, image_name: str) -> ImageState:
        """        查询镜像元数据；必要时触发远程元数据获取。

        参数：
        - ``image_name``：规范化后的镜像名。

        返回：
        - 镜像大小和分布状态。
        """
        if self.image_states[image_name] is None:
            self.image_states[image_name] = self.retrieve_image_state(image_name)
        return self.image_states[image_name]

    def retrieve_image_state(self, image_name):
        """        远程获取镜像元数据的扩展入口。

        当前 faas-sim 实验通常在启动前把镜像大小写入 ``image_states``，因此默认实现不访问
        Docker Registry。若后续需要接入真实镜像仓库，可在子类中实现该方法。
        """
        raise NotImplemented("Remote requested size information about images are not yet supported.")

    def get_dl_bandwidth(self, from_node: str, to_node: str) -> float:
        """返回从 ``from_node`` 到 ``to_node`` 的下载方向带宽，单位为字节/秒。"""
        return self.bandwidth[from_node][to_node]

    def get_image_sizes(self, pod: Pod, arch='amd64') -> Dict[str, int]:
        """        返回 Pod 所需镜像在指定架构下的大小表。

        参数：
        - ``pod``：待部署 Pod；
        - ``arch``：目标 CPU 架构，默认为 ``amd64``。

        返回：
        - ``{image_name: size_bytes}`` 字典。
        """
        return {container.image: self.get_image_state(container.image).size[arch] for container in pod.spec.containers}
