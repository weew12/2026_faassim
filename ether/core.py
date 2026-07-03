"""Ether 网络仿真核心文件，定义节点、容量、连接、路由、链路、流以及带宽重分配算法，是 faas-sim 镜像拉取、数据传输和网络时延模拟的底层实现。"""

import abc
import logging
from typing import List, Dict, NamedTuple, Union, AnyStr, Optional

import numpy as np
import simpy
from srds import ParameterizedDistribution

logger = logging.getLogger(__name__)

# 透明链路类型别名，表示交换机、路由器、互联网骨干等不直接消耗计算资源的辅助顶点。
TransparentLink = AnyStr
"""透明链路表示交换机、路由器、互联网骨干等辅助顶点；它们参与路由连通性，但不直接作为计算节点。"""

# 拓扑顶点联合类型，可为计算节点、链路对象或透明链路标识。
NetworkNode = Union['Node', 'Link', TransparentLink]
"""网络顶点可以是计算节点、链路对象或透明链路标识，是 Ether 拓扑图中的统一顶点类型。"""


class Connection(NamedTuple):
    """拓扑边数据结构，表示两个网络顶点之间的一段物理或逻辑连接，并保存固定时延或随机时延分布。"""
    # 连接、路由或流的源节点。
    source: NetworkNode
    # 连接的目标顶点。
    target: NetworkNode
    # 固定单向链路时延。
    latency: float = 0
    # 随机链路时延分布，用于每次路由查询或连接建立时采样。
    latency_dist: ParameterizedDistribution = None

    # 后续可在此扩展更细粒度的 QoS 模型，例如丢包、抖动或协议差异。

    def get_latency(self) -> float:
        """
        返回本连接本次使用的单向时延；若配置了随机分布，则从分布中采样。

        返回：单向时延数值。

        """
        if self.latency_dist:
            return self.latency_dist.sample()
        return self.latency

    def get_mode_latency(self) -> float:
        """
        返回时延分布的众数近似值，用于路由缓存阶段生成稳定的基准 RTT。

        返回：时延分布众数近似值。

        """
        if self.latency_dist:
            dist = self.latency_dist
            # 当前实现按对数正态分布近似计算众数，适配内置的链路时延分布。
            return np.exp(np.log(dist.scale) - dist.args[0] ** 2) + dist.loc
        return self.latency

    def get_mean_latency(self) -> float:
        """
        返回连接的平均时延，用于统计分析或稳定估计。

        返回：平均时延。

        """
        if self.latency_dist:
            return self.latency_dist.mean()
        return self.latency


class Capacity:
    """计算节点容量对象，用 CPU 毫核和内存字节数描述节点可承载的基础资源。"""

    def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1024 * 1024 * 1024):
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - cpu_millis：CPU 容量，单位为 millicores，用于描述节点可调度计算资源。
        - memory：内存容量，单位为字节，用于描述节点可调度内存资源。
        """
        # 内存容量，单位为字节。
        self.memory = memory
        # CPU 容量，单位为 millicores。
        self.cpu_millis = cpu_millis

    def __str__(self):
        """
        返回便于日志输出和调试查看的字符串描述。

        """
        return 'Capacity(CPU: {0} Memory: {1})'.format(self.cpu_millis, self.memory)


class Coordinate(abc.ABC):
    """节点坐标抽象接口，要求子类实现到另一个坐标的距离计算。"""
    def distance_to(self, other: 'Coordinate') -> float:
        """
        计算当前坐标或节点到另一个坐标/节点的距离。

        参数：
        - other：另一个坐标或节点，用于计算距离。

        返回：两个坐标或节点之间的距离估计。

        """
        pass


class Node:
    """网络中的计算或存储节点，保存节点名称、资源容量、CPU 架构、调度标签和可选地理/虚拟坐标。"""
    # 业务名称或拓扑标识，用于日志、图顶点和调度标签引用。
    name: str
    # 节点可用资源容量，包含 CPU 毫核和内存字节数。
    capacity: Capacity
    # 节点 CPU 架构，用于匹配容器镜像架构和调度约束。
    arch: str
    # 节点标签集合，用于描述设备类型、型号、加速器和其他调度能力。
    labels: Dict[str, str]
    # 节点的地理坐标或虚拟网络坐标，用于距离/延迟估计。
    coordinate: Optional[Coordinate]

    def __init__(self, name: str, capacity: Capacity = None, arch='x86', labels: Dict[str, str] = None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。
        - capacity：节点资源容量；为空时使用默认 Capacity。
        - arch：CPU 架构标签，用于函数镜像或设备能力匹配。
        - labels：节点标签集合，描述设备类型、型号和加速器能力。
        """
        super().__init__()
        # 业务名称或拓扑标识，用于日志、图顶点和调度标签引用。
        self.name = name
        # 节点可用资源容量，包含 CPU 毫核和内存字节数。
        self.capacity = capacity or Capacity()
        # 节点 CPU 架构，用于匹配容器镜像架构和调度约束。
        self.arch = arch
        # 节点标签集合，用于描述设备类型、型号、加速器和其他调度能力。
        self.labels = labels or dict()
        # 节点的地理坐标或虚拟网络坐标，用于距离/延迟估计。
        self.coordinate = None

    def __repr__(self):
        """
        返回对象的调试字符串表示。

        """
        return self.name

    def distance_to(self, other: 'Node') -> float:
        """
        计算当前坐标或节点到另一个坐标/节点的距离。

        参数：
        - other：另一个坐标或节点，用于计算距离。

        返回：两个坐标或节点之间的距离估计。

        """
        if self.coordinate is None:
            raise AssertionError('node has no coordinate set')
        if other.coordinate is None:
            raise AssertionError('other node has no coordinate set')

        return self.coordinate.distance_to(other.coordinate)

    def __hash__(self):
        """
        基于节点名称计算哈希值，使节点能够作为字典键和图顶点稳定使用。

        """
        return hash(self.name)


class Route:
    """从源节点到目标节点的一条网络路由，保存完整路径、路径中的链路跳点以及往返时延 RTT。"""
    # 连接、路由或流的源节点。
    source: Node
    # 路由或流量传输的目标节点。
    destination: Node
    # 最短路径解析得到的完整拓扑顶点序列。
    path: List
    # 路径中真正承载带宽的 Link 链路列表。
    hops: List['Link']
    # 往返时延，单位为毫秒。
    rtt: float = 0  # RTT 往返时延，单位为毫秒。

    def __init__(self, source: Node, destination: Node, path: list, rtt: float = 0) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - source：路由、连接或测量数据的源端。
        - destination：路由或网络流传输的目标节点。
        - path：最短路径结果，包含从源到目的的所有拓扑顶点。
        - rtt：路径往返时延，单位为毫秒。
        """
        super().__init__()
        # 连接、路由或流的源节点。
        self.source = source
        # 路由或流量传输的目标节点。
        self.destination = destination
        # 最短路径解析得到的完整拓扑顶点序列。
        self.path = path
        # 路径中真正承载带宽的 Link 链路列表。
        self.hops = [hop for hop in path if isinstance(hop, Link)]
        # 往返时延，单位为毫秒。
        self.rtt = rtt

    def __str__(self) -> str:
        """
        返回便于日志输出和调试查看的字符串描述。

        """
        return f'Route[{self.source} ->{self.hops}-> {self.destination} (rtt={self.rtt})]'

    def __copy__(self):
        """
        复制当前路由对象，避免后续随机时延采样修改共享缓存。

        """
        return Route(self.source, self.destination, self.path, self.rtt)


class Flow:
    """一次网络数据传输过程，按照路由链路的可用带宽推进 SimPy 时间，并在新流加入/结束时重新计算剩余传输时间。"""
    # 当前流已经完成传输的字节数。
    sent: int
    # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
    size: int
    # 本次网络流使用的端到端路由。
    route: Route

    # 承载该网络流的 SimPy 进程对象。
    process: simpy.Process

    def __init__(self, env: simpy.Environment, size: int, route: Route) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - env：SimPy 仿真环境，用于创建进程和推进仿真时间。
        - size：网络流传输字节数或场景单元规模，具体含义由调用位置决定。
        - route：网络流使用的端到端路由。
        """
        super().__init__()
        # SimPy 仿真环境，用于创建进程和推进离散事件时间。
        self.env = env
        # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
        self.size = size  # 数据大小单位为字节，后续传输时间由 size / goodput 得到。
        # 本次网络流使用的端到端路由。
        self.route = route
        # 当前流已经完成传输的字节数。
        self.sent = 0

    def start(self):
        """
        把网络流注册为 SimPy 进程并启动传输协程。

        返回：已启动的 SimPy 进程。

        """
        # 承载该网络流的 SimPy 进程对象。
        # 将网络流主逻辑注册到 SimPy 事件队列，仿真时钟由 run() 中的 timeout 推进。
        self.process = self.env.process(self.run())
        return self.process

    def get_goodput_bps(self):
        """
        根据路由中每条链路分配给该流的带宽，计算端到端瓶颈 goodput。

        返回：当前流在端到端瓶颈链路上的 goodput，单位为 B/s。

        """
        return min([link.get_goodput_bps(self) for link in self.route.hops])

    def run(self):
        """
        执行网络流传输主逻辑，包括连接建立、带宽登记、传输等待、中断重算和完成后的链路释放。

        """
        # SimPy 仿真环境，用于创建进程和推进离散事件时间。
        env = self.env
        size = self.size
        route = self.route
        # 连接、路由或流的源节点。
        source = route.source
        # 路径中真正承载带宽的 Link 链路列表。
        hops = route.hops
        sink = route.destination

        if not hops:
            raise ValueError('no hops in route from %s to %s' % (source, sink))

        timer = env.now
        connection_time = ((route.rtt * 1.5) / 1000)  # 用 1.5 倍 RTT 粗略近似 TCP 建连/握手耗时。
        if connection_time > 0:
            # SimPy 在这里推进建连耗时，现实含义接近 TCP 握手等待。
            yield env.timeout(connection_time)

        # 新流加入路径链路后，所有共享链路的流需要重新分配带宽。
        add_and_rebalance(self)
        goodput = self.get_goodput_bps()

        if goodput <= 0:
            raise ValueError
        # 根据剩余字节数和当前 goodput 计算本轮仿真等待时间。
        bytes_remaining = self.size
        transmission_time = bytes_remaining / goodput  # 剩余传输时间，单位为秒。

        try:
            while True:
                started = env.now

                try:
                    logger.debug('%-5.2f sending %s -[%d]-> {%s} at %d bytes/sec',
                                 env.now, source.name, size, sink.name, goodput)
                    # SimPy 在这里推进数据传输耗时，若期间带宽变化会被 Interrupt 打断。
                    yield env.timeout(transmission_time)
                    break
                except simpy.Interrupt as interrupt:
                    self.sent += goodput * (env.now - started)
                    if self.sent >= size:
                        break  # 虽然收到带宽重分配中断，但按已发送字节判断数据已经传完。

                    bytes_remaining = size - self.sent
                    logger.debug('%-5.2f sending %s -[%d]-> {%s} interrupted, new bw = %.2f (sent: %d, remaining: %d)',
                                 env.now, source.name, size, sink.name, interrupt.cause, self.sent, bytes_remaining)

                    goodput = self.get_goodput_bps()
                    if goodput <= 0:
                        raise ValueError
                    transmission_time = bytes_remaining / goodput  # 带宽变化后重新计算剩余传输时间。

            logger.debug('%-5.2f sending %s -[%d]-> {%s} completed in %.2fs',
                         env.now, source.name, size, sink.name, env.now - timer)
        finally:
            # 流结束或异常退出时释放链路占用，避免后续传输继续看到旧带宽。
            remove_and_rebalance(self)

    def establish(self):
        """
        仅模拟连接建立阶段，按 RTT 估算 TCP 握手耗时。

        """
        env = self.env
        route = self.route

        connection_time = ((route.rtt * 1.5) / 1000)  # 用 1.5 倍 RTT 粗略近似 TCP 建连/握手耗时。
        while connection_time > 0:
            started = env.now
            try:
                # SimPy 在这里推进建连耗时，现实含义接近 TCP 握手等待。
                yield env.timeout(connection_time)
                break
            except simpy.Interrupt:
                connection_time = connection_time - (env.now - started)


class Link:
    """网络链路对象，保存链路带宽、标签、当前承载的流和基于公平共享计算得到的每流可分配带宽。"""
    # 链路标称带宽，单位为 Mbit/s。
    bandwidth: int  # 链路带宽单位为 Mbit/s。
    # 链路标签，通常记录链路名称、类型或场景来源。
    tags: dict

    # 以下字段由带宽重分配流程动态维护。
    # 当前链路上每个活跃流获得的带宽分配。
    allocation: Dict[Flow, float]
    # 当前链路上活跃网络流数量。
    num_flows: int
    # 当前公平分配后单个流最多可获得的带宽。
    max_allocatable: float

    def __init__(self, bandwidth: int = 100, tags=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - bandwidth：链路标称带宽，单位为 Mbit/s。
        - tags：链路标签，用于标识链路类型、名称和场景来源。
        """
        super().__init__()
        # 链路标称带宽，单位为 Mbit/s。
        self.bandwidth = bandwidth
        # 链路标签，通常记录链路名称、类型或场景来源。
        self.tags = tags or dict()

        # 当前链路上每个活跃流获得的带宽分配。
        self.allocation = dict()
        # 当前链路上活跃网络流数量。
        self.num_flows = 0
        # 当前公平分配后单个流最多可获得的带宽。
        self.max_allocatable = bandwidth

    def recalculate_max_allocatable(self):
        """
        根据当前链路上的活跃流和已有分配，重新计算新一轮公平共享下每个流最多可获得的带宽。

        """
        num_flows = self.num_flows
        bandwidth = self.bandwidth

        if num_flows == 0:
            self.max_allocatable = bandwidth
            return

        # fair_per_flow 表示在所有流均等竞争时，每个流可获得的基准公平带宽。
        fair_per_flow = bandwidth / num_flows

        # 已分配且需求低于公平值的流继续保留原分配，避免无意义抢占。
        reserved = {k: v for k, v in self.allocation.items() if v < fair_per_flow}
        allocatable = bandwidth - sum(reserved.values())

        # 剩余流继续竞争未被保留的链路带宽。
        competing_flows = num_flows - len(reserved)
        if competing_flows:
            allocatable_per_flow = allocatable / competing_flows
        else:
            allocatable_per_flow = allocatable

        self.max_allocatable = max(fair_per_flow, allocatable_per_flow)

    def get_goodput_bps(self, flow: Flow):
        """
        根据路由中每条链路分配给该流的带宽，计算端到端瓶颈 goodput。

        参数：
        - flow：需要加入、移除或重新分配带宽的网络流对象。

        返回：当前流在端到端瓶颈链路上的 goodput，单位为 B/s。

        """
        # 当前 goodput 模型保留为轻量近似，便于大规模仿真。
        # 可在此引入 TCP 多流退化函数，进一步模拟大量并发流带来的协议开销。

        if flow not in self.allocation:
            return None

        allocated = self.allocation[flow]
        practical_bw = allocated * 125000
        goodput_magic_number = 0.97  # rough estimate of goodput (~ TCP overhead)

        return practical_bw * goodput_magic_number

    def __str__(self) -> str:
        """
        返回便于日志输出和调试查看的字符串描述。

        """
        return f'Link({hex(id(self))}){self.tags}'

    def __repr__(self):
        """
        返回对象的调试字符串表示。

        """
        return self.__str__()


def remove_and_rebalance(flow: Flow):
    # 先收集与该流共享链路的受影响流和链路，再统一更新带宽。
    """
    从路径链路中移除一个已结束流，并通知受影响的其他流重新计算带宽。

    参数：
    - flow：需要加入、移除或重新分配带宽的网络流对象。

    """
    affected_flows, affected_links = collect_subnet(flow)
    affected_flows.remove(flow)

    for link in flow.route.hops:
        link.num_flows -= 1
        del link.allocation[flow]
        link.recalculate_max_allocatable()

    rebalance(flow, affected_flows, affected_links)


def add_and_rebalance(flow: Flow):
    # 先收集与该流共享链路的受影响流和链路，再统一更新带宽。
    """
    把新流加入路径链路，并对与其共享链路的相关流执行带宽重分配。

    参数：
    - flow：需要加入、移除或重新分配带宽的网络流对象。

    """
    affected_flows, affected_links = collect_subnet(flow)

    for link in flow.route.hops:
        link.num_flows += 1
        link.recalculate_max_allocatable()

    rebalance(flow, affected_flows, affected_links)


def rebalance(triggering_flow, affected_flows, affected_links):
    # 保存本轮发生变化的带宽分配，用于随后中断相关流并触发重算。
    """
    基于瓶颈链路和最大最小公平原则，为受影响流重新分配带宽并中断需要调整的 SimPy 进程。

    参数：
    - triggering_flow：触发本轮带宽重分配的网络流。
    - affected_flows：与触发流共享链路、需要重新评估带宽的流集合。
    - affected_links：受本轮流量变化影响的链路集合。

    返回：本轮发生变化的流到带宽分配映射。

    """
    allocation: Dict[Flow, float] = dict()

    while affected_flows:
        bottlenecks = {flow: min([link.max_allocatable for link in flow.route.hops]) for flow in affected_flows}
        flow: Flow = min(bottlenecks, key=lambda k: bottlenecks[k])
        request = bottlenecks[flow]

        changed = False

        for link in flow.route.hops:
            if link.allocation.get(flow) == request:
                continue
            changed = True
            link.allocation[flow] = request
            link.recalculate_max_allocatable()

        if changed:
            allocation[flow] = request

        del bottlenecks[flow]
        affected_flows.remove(flow)

    for flow, bw in allocation.items():
        if flow is triggering_flow:
            continue
        if not flow.process.is_alive:
            continue
        flow.process.interrupt(bw)

    # logger.info(' >> new allocation:')
    # for link in affected_links:
    #     logger.info(' - %s (%.2f)', link, link.bandwidth)
    #     for flow, bw in link.allocation.items():
    #         logger.info('   - %8.2f %s', bw, flow.route)

    return allocation


def remove_without_rebalance(flow: Flow):
    """
    移除非抢占式流占用的链路带宽，但不主动打断其他流。

    参数：
    - flow：需要加入、移除或重新分配带宽的网络流对象。

    """
    for link in flow.route.hops:
        link.num_flows -= 1
        del link.allocation[flow]
        link.recalculate_max_allocatable()


def add_without_rebalance(flow: Flow):
    """
    为非抢占式流按当前可用瓶颈带宽登记链路分配，不触发全局重平衡。

    参数：
    - flow：需要加入、移除或重新分配带宽的网络流对象。

    """
    allocated_bandwidth = min([link.max_allocatable for link in flow.route.hops])

    for link in flow.route.hops:
        link.num_flows += 1
        link.recalculate_max_allocatable()
        link.allocation[flow] = allocated_bandwidth

# 非抢占式流实现，适合不希望中断已有流的近似网络仿真场景。
class UninterruptingFlow(Flow):
    """非抢占式网络流变体，在传输过程中不主动中断已有流，只按加入时的带宽估算本次传输时间。"""
    def __init__(self, *args, **kwargs):
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。
        """
        super().__init__(*args, **kwargs)

    def run(self):
        """
        执行网络流传输主逻辑，包括连接建立、带宽登记、传输等待、中断重算和完成后的链路释放。

        """
        # SimPy 仿真环境，用于创建进程和推进离散事件时间。
        env = self.env
        # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
        size = self.size
        # 本次网络流使用的端到端路由。
        route = self.route
        # 连接、路由或流的源节点。
        source = route.source
        # 路径中真正承载带宽的 Link 链路列表。
        hops = route.hops
        sink = route.destination

        if not hops:
            raise ValueError('no hops in route from %s to %s' % (source, sink))

        timer = env.now
        connection_time = ((route.rtt * 1.5) / 1000)  # 用 1.5 倍 RTT 粗略近似 TCP 建连/握手耗时。
        if connection_time > 0:
            # SimPy 在这里推进建连耗时，现实含义接近 TCP 握手等待。
            yield env.timeout(connection_time)

        add_without_rebalance(self)
        goodput = self.get_goodput_bps()

        if goodput <= 0:
            raise ValueError
        # 根据剩余字节数和当前 goodput 计算本轮仿真等待时间。
        bytes_remaining = self.size
        transmission_time = bytes_remaining / goodput  # 剩余传输时间，单位为秒。

        try:
            while True:
                started = env.now

                try:
                    logger.debug('%-5.2f sending %s -[%d]-> {%s} at %d bytes/sec',
                                 env.now, source.name, size, sink.name, goodput)
                    # SimPy 在这里推进数据传输耗时，若期间带宽变化会被 Interrupt 打断。
                    yield env.timeout(transmission_time)
                    break
                except simpy.Interrupt as interrupt:
                    self.sent += goodput * (env.now - started)
                    if self.sent >= size:
                        break  # 虽然收到带宽重分配中断，但按已发送字节判断数据已经传完。

                    bytes_remaining = size - self.sent
                    logger.debug('%-5.2f sending %s -[%d]-> {%s} interrupted, new bw = %.2f (sent: %d, remaining: %d)',
                                 env.now, source.name, size, sink.name, interrupt.cause, self.sent, bytes_remaining)

                    goodput = self.get_goodput_bps()
                    if goodput <= 0:
                        raise ValueError
                    transmission_time = bytes_remaining / goodput  # 带宽变化后重新计算剩余传输时间。

            logger.debug('%-5.2f sending %s -[%d]-> {%s} completed in %.2fs',
                         env.now, source.name, size, sink.name, env.now - timer)
        finally:
            remove_without_rebalance(self)


def collect_subnet(flow: Flow):
    # 先收集与该流共享链路的受影响流和链路，再统一更新带宽。
    """
    从触发流出发，沿共享链路和流关系搜索所有受影响的流与链路。

    参数：
    - flow：需要加入、移除或重新分配带宽的网络流对象。

    返回：受影响流集合和受影响链路集合。

    """
    affected_links = set()
    affected_flows = set()

    stack = set()
    stack.add(flow)

    while stack:
        elem = stack.pop()
        if isinstance(elem, Link):
            if elem in affected_links:
                continue
            affected_links.add(elem)

            flows = elem.allocation.keys()
            stack.update(flows)

        elif isinstance(elem, Flow):
            if elem in affected_flows:
                continue
            affected_flows.add(elem)

            links = elem.route.hops
            stack.update(links)
        else:
            raise ValueError('element of type %s not handled: %s' % (type(elem), elem))

    return affected_flows, affected_links
