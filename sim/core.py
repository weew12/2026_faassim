"""
文件作用：仿真运行环境和节点状态文件，集中保存 SimPy 环境、拓扑、FaaS 系统、调度器、资源状态、指标记录器和节点运行时状态。
主要类：NodeState、SimulationTimeoutError、Environment。
主要函数：timeout_listener。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import time
from typing import Set, Optional, Any, Generator, Callable, List, Dict

import numpy as np
import simpy
from ether.core import Node as EtherNode, Capacity
from sklearn.base import RegressorMixin

from .degradation import create_degradation_model_input
from .oracle.oracle import ResourceOracle

# 字段说明：Node：表示 node，在当前业务流程中作为输入参数、状态字段或计算结果使用。
Node = EtherNode


class NodeState:
    """
    类作用：节点运行时状态，记录镜像缓存、当前调用、历史调用和性能退化模型。
    核心字段：docker_images：节点上已经缓存的容器镜像集合，用于避免重复拉取镜像。；current_requests：节点当前正在执行的函数调用记录，用于并发和干扰计算。；all_requests：节点历史函数调用记录，用于窗口查询和指标分析。；performance_degradation：节点级性能退化模型，用于估计多租户资源竞争造成的执行时间放大。。
    核心方法：__init__、estimate_degradation、clean_up、set_end、name、arch、capacity、get_calls_in_timeframe。
    """
    # 字段说明：docker_images：节点上已经缓存的容器镜像集合，用于避免重复拉取镜像。
    docker_images: Set
    # 字段说明：current_requests：节点当前正在执行的函数调用记录，用于并发和干扰计算。
    current_requests: Set
    # 字段说明：all_requests：节点历史函数调用记录，用于窗口查询和指标分析。
    all_requests: List[any]
    # 字段说明：performance_degradation：节点级性能退化模型，用于估计多租户资源竞争造成的执行时间放大。
    performance_degradation: Optional[RegressorMixin]

    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：all_requests、buffer_limit、buffer_size、cache、current_requests、docker_images、ether_node、performance_degradation、skippy_node。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.ether_node：Ether 拓扑中的节点对象，保存网络和容量属性。
        self.ether_node = None
        # 字段说明：self.skippy_node：Skippy 调度器中的节点表示，与 Ether 节点一一对应。
        self.skippy_node = None
        # 字段说明：self.docker_images：节点上已经缓存的容器镜像集合，用于避免重复拉取镜像。
        self.docker_images = set()
        # 字段说明：self.current_requests：节点当前正在执行的函数调用记录，用于并发和干扰计算。
        self.current_requests = set()
        # 字段说明：self.all_requests：节点历史函数调用记录，用于窗口查询和指标分析。
        self.all_requests = []
        # 字段说明：self.performance_degradation：节点级性能退化模型，用于估计多租户资源竞争造成的执行时间放大。
        self.performance_degradation = None
        # 字段说明：self.buffer_size：缓冲区大小，用于网络、日志或资源窗口数据暂存。
        self.buffer_size = 0
        # 字段说明：self.buffer_limit：缓冲区上限，限制记录或数据暂存规模。
        self.buffer_limit = 50
        # 字段说明：self.cache：缓存表，避免重复构造昂贵对象或重复计算调度/网络结果。
        self.cache = {}

    def estimate_degradation(self, resource_oracle: ResourceOracle,
                             start_ts: int, end_ts: int) -> float:
        """
        函数作用：基于节点并发调用状态估计当前函数执行的性能退化倍数。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。；start_ts：表示 start、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。；end_ts：表示 end、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：移除已结束的历史调用，避免旧调用影响后续退化估计。
        关键流程：
        - 写入对象字段：buffer_size。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
            # 字段说明：self.buffer_size：缓冲区大小，用于网络、日志或资源窗口数据暂存。
            self.buffer_size = self.buffer_size - len(remove_candidates)
        self.buffer_size += 1

    def set_end(self, request_id, end):
        """
        函数作用：给指定请求对应的调用记录写入结束时间。
        参数：request_id：函数调用请求的唯一编号。；end：函数调用结束时间。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        for call in self.all_requests:
            if call.request_id == request_id:
                call.end = end

        self.clean_up()

    @property
    def name(self):
        """
        函数作用：返回对象在业务域中的稳定名称。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.ether_node.name

    @property
    def arch(self):
        """
        函数作用：处理 arch 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.ether_node.arch

    @property
    def capacity(self) -> Capacity:
        """
        函数作用：处理 capacity 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.ether_node.capacity

    def get_calls_in_timeframe(self, start_ts, end_ts) -> List:
        """
        函数作用：查询指定时间窗口内仍相关的函数调用记录。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：start_ts：表示 start、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。；end_ts：表示 end、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
    类作用：SimulationTimeoutError 类，封装 simulation、timeout、error 相关状态和业务操作。
    继承关系：BaseException。
    """
    pass


class Environment(simpy.Environment):
    """
    类作用：仿真全局上下文，持有 SimPy 环境、拓扑、FaaS 系统、调度器、资源状态、指标器等组件引用。
    继承关系：simpy.Environment。
    核心字段：cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。；faas：FaaS 系统实例，负责函数部署、调用、扩缩容和副本生命周期管理。。
    核心方法：__init__、get_node_state。
    """
    # 字段说明：cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。
    cluster: 'SimulationClusterContext'
    # 字段说明：faas：FaaS 系统实例，负责函数部署、调用、扩缩容和副本生命周期管理。
    faas: 'FaasSystem'

    def __init__(self, initial_time=0):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：background_processes、benchmark、cluster、container_registry、degradation_models、faas、metrics、metrics_server、node_states、resource_monitor、resource_state、scheduler、simulator_factory、storage_index、topology。
        参数：initial_time：表示 initial、time，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__(initial_time)
        # 字段说明：self.faas：FaaS 系统实例，负责函数部署、调用、扩缩容和副本生命周期管理。
        self.faas = None
        # 字段说明：self.simulator_factory：函数模拟器工厂，根据函数定义创建具体 FunctionSimulator。
        self.simulator_factory = None
        # 字段说明：self.topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
        self.topology = None
        # 字段说明：self.storage_index：存储节点索引，用于模拟函数输入/输出数据传输。
        self.storage_index = None
        # 字段说明：self.benchmark：实验场景对象，定义镜像注册、函数部署和请求生成逻辑。
        self.benchmark = None
        # 字段说明：self.cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。
        self.cluster = None
        # 字段说明：self.container_registry：容器镜像仓库，保存可拉取镜像及其大小、架构信息。
        self.container_registry = None
        # 字段说明：self.metrics：结构化指标记录器。
        self.metrics = None
        # 字段说明：self.scheduler：函数副本调度器，决定副本放置到哪个节点。
        self.scheduler = None
        # 字段说明：self.node_states：按节点名称索引的运行时状态表。
        self.node_states = dict()
        # 字段说明：self.metrics_server：资源窗口指标服务器，提供平均 CPU/资源利用率查询。
        self.metrics_server = None
        # 字段说明：self.resource_state：全局资源状态表，记录副本在节点上的资源占用。
        self.resource_state = None
        # 字段说明：self.resource_monitor：资源监控后台进程对象。
        self.resource_monitor = None
        # 字段说明：self.background_processes：后台 SimPy 进程列表，例如资源监控器和自动伸缩器。
        self.background_processes: List[Callable[[Environment], Generator[simpy.events.Event, Any, Any]]] = []
        # 字段说明：self.degradation_models：节点级性能退化模型集合，用于多租户干扰预测。
        self.degradation_models: Dict[str, Optional[RegressorMixin]] = {}

    def get_node_state(self, name: str) -> Optional[NodeState]:
        """
        函数作用：读取或创建指定节点的运行时状态对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：name：对象名称。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：监听仿真超时事件，到达时间上限后停止仿真。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；started：表示 started，在当前业务流程中作为输入参数、状态字段或计算结果使用。；max_time：表示 max、time，在当前业务流程中作为输入参数、状态字段或计算结果使用。；interval：轮询或采样间隔。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    while True:
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(interval)

        if (time.time() - started) > max_time:
            raise SimulationTimeoutError()
