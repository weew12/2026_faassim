"""
仿真全局环境与节点运行时状态。

本模块在 SimPy Environment 之上增加 faas-sim 所需的业务上下文：拓扑、FaaS 系统、调度器、容器仓库、资源状态、指标系统、节点状态和后台进程列表。
NodeState 负责记录单个节点上的镜像缓存、正在执行的请求、历史请求以及性能退化模型输入。

阅读建议：先看 Environment 如何挂载组件，再看 NodeState 如何支持镜像缓存、请求历史和性能退化。
"""

import time
from typing import Set, Optional, Any, Generator, Callable, List, Dict

import numpy as np
import simpy
from ether.core import Node as EtherNode, Capacity
from sklearn.base import RegressorMixin

from .degradation import create_degradation_model_input
from .oracle.oracle import ResourceOracle

Node = EtherNode


class NodeState:
    """
    单个仿真节点的运行时状态。

    保存 Ether 节点、Skippy 节点、已缓存镜像、当前请求、历史请求和性能退化模型。性能退化估计会读取时间窗口内的并发调用并构造模型输入。

    重要字段：
    - docker_images: 当前节点已经缓存的镜像集合；镜像拉取时会先查这里避免重复传输。
    - current_requests: 当前正在该节点上执行的函数请求集合。
    - all_requests: 节点历史请求列表，性能退化模型会按时间窗口读取这里的并发请求。
    - performance_degradation: 可选的 sklearn 回归模型，用于根据并发和资源画像预测性能退化。
    - ether_node: 原始 Ether 节点对象，保存网络拓扑和容量信息。
    - skippy_node: Skippy 节点视图，供调度器读取容量、标签和可分配资源。
    - buffer_size: 历史请求缓存的当前计数，用于触发清理逻辑。
    - buffer_limit: 历史请求缓存清理阈值。
    - cache: 性能退化估计缓存，避免重复计算同一时间窗口。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    docker_images: Set
    current_requests: Set
    all_requests: List[any]
    performance_degradation: Optional[RegressorMixin]

    def __init__(self) -> None:
        """
        初始化 NodeState 对象。

        主要建立字段：ether_node、skippy_node、docker_images、current_requests、all_requests、performance_degradation、buffer_size、buffer_limit、cache。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.ether_node = None
        self.skippy_node = None
        self.docker_images = set()
        self.current_requests = set()
        self.all_requests = []
        self.performance_degradation = None
        self.buffer_size = 0
        self.buffer_limit = 50
        self.cache = {}

    def estimate_degradation(self, resource_oracle: ResourceOracle,
                             start_ts: int, end_ts: int) -> float:
        """
        估计当前节点在给定时间窗口内的性能退化比例。

        方法会先按四舍五入后的起止时间查缓存；缓存未命中时，收集窗口内重叠的历史请求，构造成退化模型输入，再调用 performance_degradation.predict。没有模型或没有有效特征时返回 0。

        参数说明：
        - resource_oracle: 资源 Oracle，用于查询函数在不同节点上的资源画像。 类型标注：ResourceOracle。
        - start_ts: 统计或估计窗口的开始仿真时间。 类型标注：int。
        - end_ts: 统计或估计窗口的结束仿真时间。 类型标注：int。

        返回说明：返回值类型标注为 float，通常作为后续调度、执行、统计或查询流程的输入。
        """
        if self.performance_degradation is not None:
            rounded_start = round(start_ts, 1)
            rounded_end = round(end_ts, 1)
            get = self.cache.get((rounded_start, rounded_end), None)
            if get is not None:
                return get

            calls = self.get_calls_in_timeframe(start_ts, end_ts)
            x = create_degradation_model_input(calls, start_ts, end_ts, self.name,
                                               self.capacity.memory, resource_oracle)

            if len(x) == 0:
                
                return 0
            x = np.array(x).reshape((1, -1))
            y = self.performance_degradation.predict(x)[0]
            self.cache[(rounded_start, rounded_end)] = y
            return y
        return 0

    def clean_up(self):
        """
        压缩节点历史请求缓存。

        当缓存达到上限时，删除已经结束且不会再被未完成请求窗口依赖的历史请求，避免退化模型的历史数据无限增长。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        if self.buffer_size >= self.buffer_limit:
            remove_candidates = [x for x in self.all_requests if x.end is not None]
            not_remove = set()
            for req in self.all_requests:
                if req.end is not None:
                    continue
                for past_request in remove_candidates:
                    if req.start < past_request.end:
                        not_remove.add(past_request)
            for req in not_remove:
                remove_candidates.remove(req)
            for req in remove_candidates:
                self.all_requests.remove(req)
            self.buffer_size = self.buffer_size - len(remove_candidates)
        self.buffer_size += 1

    def set_end(self, request_id, end):
        """
        为指定请求记录结束时间。

        调用执行结束后根据 request_id 找到历史请求并写入 end，然后触发 clean_up 清理旧请求。

        参数说明：
        - request_id: 请求唯一编号，用于在历史请求中定位对应调用。
        - end: 请求结束的仿真时间。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        for call in self.all_requests:
            if call.request_id == request_id:
                call.end = end

        self.clean_up()

    @property
    def name(self):
        """
        返回对象的名称字段。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.ether_node.name

    @property
    def arch(self):
        """
        返回节点 CPU 架构，用于镜像兼容性和调度判断。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.ether_node.arch

    @property
    def capacity(self) -> Capacity:
        """
        返回 Ether 节点容量对象，包含 CPU、内存等资源上限。

        返回说明：返回值类型标注为 Capacity，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.ether_node.capacity

    def get_calls_in_timeframe(self, start_ts, end_ts) -> List:
        """
        查询与时间窗口发生重叠的请求。

        只要请求在 start_ts 前已经开始且窗口开始时仍未结束，或请求在窗口内部开始，都会被认为会影响该窗口的并发退化估计。

        参数说明：
        - start_ts: 统计或估计窗口的开始仿真时间。
        - end_ts: 统计或估计窗口的结束仿真时间。

        返回说明：返回值类型标注为 List，通常作为后续调度、执行、统计或查询流程的输入。
        """
        calls = []
        for call in self.all_requests:
            if call.start <= start_ts:
                
                if call.end is None or call.end > start_ts:
                    calls.append(call)
            else:
                
                if call.start < end_ts:
                    calls.append(call)
        return calls


class SimulationTimeoutError(BaseException):
    """
    仿真超时控制异常。

    timeout_listener 在达到最大仿真时长后抛出该异常，用于从运行循环中显式退出。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    pass


class Environment(simpy.Environment):
    """
    faas-sim 全局仿真环境。

    继承 SimPy Environment，并挂载拓扑、FaaS 系统、调度器、容器仓库、资源状态、指标器、监控器、Benchmark 和节点状态表等业务组件。

    重要字段：
    - cluster: Skippy 集群上下文适配器，把 faas-sim 的拓扑和资源状态暴露给调度器。
    - faas: FaaS 平台实现，负责部署、调用、扩缩容和副本生命周期管理。
    - simulator_factory: 函数模拟器工厂，用于为每个新副本创建生命周期模拟器。
    - topology: Ether 拓扑对象，描述节点、链路和路由关系。
    - storage_index: Skippy 存储索引，用于描述数据所在节点。
    - benchmark: 实验场景对象，负责注册镜像、部署函数并产生请求负载。
    - container_registry: 容器镜像仓库，按镜像名、tag 和架构保存镜像大小等元数据。
    - metrics: 指标中心，用于记录部署、调度、调用、网络和资源利用率事件。
    - scheduler: Skippy 调度器，负责为待启动 Pod 选择运行节点。
    - node_states: 节点名到 NodeState 的缓存，用于保存镜像缓存、运行请求和退化模型状态。
    - metrics_server: 资源窗口服务，保存周期性资源采样并计算平均利用率。
    - resource_state: 全局资源占用表，记录每个节点上各函数副本占用的 CPU、内存等资源。
    - resource_monitor: 资源监控后台进程，周期性读取 resource_state 并写入 metrics_server。
    - background_processes: 需要随 FaaS 系统一起启动的后台 SimPy 进程列表。
    - degradation_models: 节点名到性能退化模型的映射，用于执行时间退化估计。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    cluster: 'SimulationClusterContext'
    faas: 'FaasSystem'

    def __init__(self, initial_time=0):
        """
        初始化 Environment 对象。

        主要建立字段：faas、simulator_factory、topology、storage_index、benchmark、cluster、container_registry、metrics、scheduler、node_states、metrics_server、resource_state、resource_monitor、background_processes、degradation_models。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - initial_time: SimPy 环境的初始仿真时间。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__(initial_time)
        self.faas = None
        self.simulator_factory = None
        self.topology = None
        self.storage_index = None
        self.benchmark = None
        self.cluster = None
        self.container_registry = None
        self.metrics = None
        self.scheduler = None
        self.node_states = dict()
        self.metrics_server = None
        self.resource_state = None
        self.resource_monitor = None
        self.background_processes: List[Callable[[Environment], Generator[simpy.events.Event, Any, Any]]] = []
        self.degradation_models: Dict[str, Optional[RegressorMixin]] = {}

    def get_node_state(self, name: str) -> Optional[NodeState]:
        """
        返回指定节点名对应的 NodeState。

        节点状态在 Environment 初始化拓扑时建立，后续部署、镜像缓存、请求执行和退化估计都通过该入口访问。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：str。

        返回说明：返回值类型标注为 Optional[NodeState]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        if name in self.node_states:
            return self.node_states[name]

        ether_node = self.topology.find_node(name) if self.topology else None
        skippy_node = self.cluster.get_node(name) if self.cluster else None

        node_state = NodeState()
        node_state.env = self
        node_state.ether_node = ether_node
        node_state.skippy_node = skippy_node

        degradation_model = self.degradation_models.get(name, None)
        if degradation_model is not None:
            node_state.performance_degradation = degradation_model

        self.node_states[name] = node_state
        return node_state


def timeout_listener(env, started, max_time, interval=1):
    """
    仿真超时监听进程。

    该协程等待 timeout 秒后抛出 SimulationTimeoutError，用于让长时间实验可以被显式截断。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
    - started: 实验开始时的真实墙钟时间。
    - max_time: 允许实验运行的最大墙钟秒数。
    - interval: 轮询或后台循环间隔，单位为仿真时间。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    while True:
        yield env.timeout(interval)

        if (time.time() - started) > max_time:
            raise SimulationTimeoutError()
