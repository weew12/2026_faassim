"""Ether 网络单元建模文件，定义 Host、LANCell、SharedLinkCell、GeoCell 等组合式拓扑构造单元，用于快速生成边缘集群、共享接入网和地理分布场景。"""

import inspect
import itertools
from collections import defaultdict
from collections.abc import Iterable
from typing import Callable, List, Union

from srds import RandomSampler, ConstantSampler, IntegerTruncationSampler, ParameterizedDistribution

from ether.qos import latency
from ether.core import Node, Link, NetworkNode
from ether.topology import Topology, Connection

# 按设备或网络单元类型维护的递增计数器，用于生成稳定唯一名称。
counters = defaultdict(lambda: itertools.count(0, 1))


class UpDownLink:
    """上下行非对称回传链路配置，保存下行带宽、上行带宽、回传目标和链路时延分布。"""
    # 下行带宽，单位为 Mbit/s。
    bw_down: int
    # 上行带宽，单位为 Mbit/s。
    bw_up: int
    # 当前网络单元连接到上级网络或互联网骨干的目标顶点。
    backhaul: NetworkNode
    # 随机链路时延分布，用于每次路由查询或连接建立时采样。
    latency_dist: ParameterizedDistribution

    def __init__(self, bw_down, bw_up=None, backhaul='internet', latency_dist=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - bw_down：下行带宽，单位为 Mbit/s。
        - bw_up：上行带宽，单位为 Mbit/s；为空时使用与下行相同的带宽。
        - backhaul：上级网络、互联网骨干或回传链路配置。
        - latency_dist：链路时延分布；为空时使用默认局域网时延。
        """
        super().__init__()
        # 下行带宽，单位为 Mbit/s。
        self.bw_down = bw_down
        # 上行带宽，单位为 Mbit/s。
        self.bw_up = bw_up if bw_up is not None else bw_down
        # 当前网络单元连接到上级网络或互联网骨干的目标顶点。
        self.backhaul = backhaul
        # 随机链路时延分布，用于每次路由查询或连接建立时采样。
        self.latency_dist = latency_dist


class Cell:
    """可组合网络单元基类，保存子节点/子单元、规模、随机性和回传连接，并提供递归物化能力。"""
    # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
    size: Union[int, RandomSampler]
    # 该网络单元包含的子节点、子单元或节点工厂函数。
    nodes = List[Union[Node, 'Cell', Callable]]
    # 拓扑生成随机性参数，保留给随机场景扩展使用。
    entropy: float

    def __init__(self, nodes=None, size=None, entropy=None, backhaul=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - nodes：当前网络单元包含的节点、子单元或节点工厂。
        - size：网络流传输字节数或场景单元规模，具体含义由调用位置决定。
        - entropy：拓扑生成随机性参数，当前主要作为扩展预留字段。
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__()
        # 该网络单元包含的子节点、子单元或节点工厂函数。
        self.nodes = nodes
        # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
        self.size = size
        # 拓扑生成随机性参数，保留给随机场景扩展使用。
        self.entropy = entropy
        # 当前网络单元连接到上级网络或互联网骨干的目标顶点。
        self.backhaul = backhaul

    def materialize(self, topology: Topology, parent=None):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - parent：当前 Cell 的父级网络单元，主要用于递归物化时保留层级关系。

        """
        raise NotImplementedError

    def generate(self) -> Topology:
        """
        创建一个新的 Topology 并把当前 Cell 物化进去。

        返回：已经物化完成的新 Topology。

        """
        t: Topology = Topology()
        self.materialize(t)
        return t

    def _materialize(self, topology: Topology, c: object, backhaul=None):
        """
        递归处理子节点、子单元或工厂函数，把它们转换为可加入拓扑的具体对象。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - c：递归物化过程中的子节点、子单元、工厂函数或列表。
        - backhaul：上级网络、互联网骨干或回传链路配置。

        """
        if isinstance(c, Iterable):
            for elem in c:
                self._materialize(topology, elem, backhaul)
            return

        if callable(c):
            # 节点或子单元工厂在物化阶段被调用，生成真实 Host/Cell 对象。
            c = c()  # 目前工厂函数不透传额外参数，复杂场景可在此扩展参数传递。

        if isinstance(c, Node):
            c = Host(c, backhaul=backhaul)
        elif isinstance(c, Cell):
            if backhaul:
                c.backhaul = backhaul

        c.materialize(topology, self)


class Host(Cell):
    """单主机网络单元，把一个计算节点接到独立链路上，并可继续连接到上级交换机或回传链路。"""
    # Host 封装的实际计算节点。
    node: Node
    # Host 或 SharedLinkCell 内部创建的接入链路。
    link: Link

    def __init__(self, node: Node, link_bw=1000, backhaul=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - link_bw：Host 到本地接入链路的带宽，单位为 Mbit/s。
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(nodes=[node], backhaul=backhaul)
        # Host 封装的实际计算节点。
        self.node = node
        # Host 到接入链路的本地链路带宽。
        self.link_bw = link_bw
        # Host 或 SharedLinkCell 内部创建的接入链路。
        self.link = Link(bandwidth=self.link_bw, tags={'name': 'link_%s' % node.name, 'type': 'node'})

    def materialize(self, topology: Topology, parent=None, latency_dist=latency.lan):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - parent：当前 Cell 的父级网络单元，主要用于递归物化时保留层级关系。
        - latency_dist：链路时延分布；为空时使用默认局域网时延。

        """
        node = self.nodes[0]

        # 把计算节点接入自己的本地链路，形成 Node -> Link 的拓扑边。
        topology.add_connection(Connection(node, self.link, latency_dist=latency_dist))
        if self.backhaul:
            # 把主机链路继续接入上级交换机或回传网络。
            topology.add_connection(Connection(self.link, self.backhaul))

    def __str__(self):
        """
        返回便于日志输出和调试查看的字符串描述。

        """
        return 'Host[node=%s, link=%s] -> %s' % (self.node, self.link, self.backhaul)

    def __repr__(self):
        """
        返回对象的调试字符串表示。

        """
        return self.__str__()


class Client(Host):
    """客户端主机快捷类型，用普通 Node 表示产生请求或访问服务的客户端。"""
    def __init__(self, name: str, **kwargs) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。
        """
        super().__init__(Node(name), **kwargs)


class Broker(Host):
    """消息代理主机快捷类型，用普通 Node 表示 MQTT 等中间件代理节点。"""
    def __init__(self, name: str, **kwargs) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。
        """
        super().__init__(Node(name), **kwargs)


class LANCell(Cell):

    """局域网单元，为一组节点创建共享交换机，并把节点链路接入交换机或回传网络。"""
    def __init__(self, nodes, backhaul=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - nodes：当前网络单元包含的节点、子单元或节点工厂。
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(nodes=nodes, backhaul=backhaul)

    def _create_identity(self):
        """
        为网络单元生成唯一名称、编号和内部交换机/共享链路标识。

        """
        # 同类网络单元的递增编号，用于生成唯一名称。
        self.nr = next(counters['lan'])
        # 业务名称或拓扑标识，用于日志、图顶点和调度标签引用。
        self.name = 'lan_%d' % self.nr
        # LANCell 内部交换机标识，用作透明拓扑顶点。
        self.switch = 'switch_%s' % self.name

    def materialize(self, topology: Topology, parent=None):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - parent：当前 Cell 的父级网络单元，主要用于递归物化时保留层级关系。

        """
        self._create_identity()

        for cell in self.nodes:
            self._materialize(topology, cell, self.switch)

        if self.backhaul:
            if isinstance(self.backhaul, UpDownLink):
                uplink = Link(self.backhaul.bw_up, tags={'type': 'uplink', 'name': 'up_%s' % self.name})
                downlink = Link(self.backhaul.bw_down, tags={'type': 'downlink', 'name': 'down_%s' % self.name})

                # LAN 上行方向接入受限 uplink，体现上行带宽和时延。
                topology.add_connection(Connection(self.switch, uplink, latency_dist=self.backhaul.latency_dist),
                                        directed=True)
                # LAN 下行方向由 downlink 进入交换机，体现上下行分离。
                topology.add_connection(Connection(downlink, self.switch), directed=True)

                topology.add_connection(Connection(self.backhaul.backhaul, downlink,
                                                   latency_dist=self.backhaul.latency_dist), directed=True)
                topology.add_connection(Connection(uplink, self.backhaul.backhaul), directed=True)

            else:
                topology.add_connection(Connection(self.switch, self.backhaul, latency_dist=latency.lan))


class SharedLinkCell(Cell):

    """共享链路单元，让多个节点共用同一条带宽受限链路，适合模拟无线接入、移动回传或资源受限边缘链路。"""
    def __init__(self, nodes, shared_bandwidth=300, backhaul=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - nodes：当前网络单元包含的节点、子单元或节点工厂。
        - shared_bandwidth：共享接入链路总带宽，单位为 Mbit/s。
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(nodes=nodes, backhaul=backhaul)
        # 共享链路总带宽，所有接入节点共同竞争该带宽。
        self.shared_bandwidth = shared_bandwidth

    def _create_identity(self):
        """
        为网络单元生成唯一名称、编号和内部交换机/共享链路标识。

        """
        # 同类网络单元的递增编号，用于生成唯一名称。
        self.nr = next(counters['shared'])
        # 业务名称或拓扑标识，用于日志、图顶点和调度标签引用。
        self.name = 'shared_%d' % self.nr
        # Host 或 SharedLinkCell 内部创建的接入链路。
        self.link = Link(bandwidth=self.shared_bandwidth, tags={'name': self.name, 'type': 'shared'})

    def materialize(self, topology: Topology, parent=None):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - parent：当前 Cell 的父级网络单元，主要用于递归物化时保留层级关系。

        """
        self._create_identity()

        for cell in self.nodes:
            self._materialize(topology, cell, self.link)

        if self.backhaul:
            if isinstance(self.backhaul, UpDownLink):
                uplink = Link(self.backhaul.bw_up, tags={'type': 'uplink', 'name': 'up_%s' % self.name})
                downlink = Link(self.backhaul.bw_down, tags={'type': 'downlink', 'name': 'down_%s' % self.name})

                # 共享链路上行接入回传 uplink，多个节点会竞争 shared link 和 uplink。
                topology.add_connection(Connection(self.link, uplink, latency_dist=self.backhaul.latency_dist), True)
                # 共享链路下行从 downlink 回到共享接入链路。
                topology.add_connection(Connection(downlink, self.link), True)

                topology.add_connection(Connection(self.backhaul.backhaul, downlink,
                                                   latency_dist=self.backhaul.latency_dist), directed=True)
                topology.add_connection(Connection(uplink, self.backhaul.backhaul), directed=True)

            else:
                # 把主机链路继续接入上级交换机或回传网络。
                topology.add_connection(Connection(self.link, self.backhaul))


class GeoCell(Cell):

    """地理分布单元，按数量和密度采样重复生成多个子单元，用于模拟城市小区或多区域分布。"""
    def __init__(self, size, density, nodes) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - size：网络流传输字节数或场景单元规模，具体含义由调用位置决定。
        - density：每个地理单元内部生成多少节点/子单元的采样器。
        - nodes：当前网络单元包含的节点、子单元或节点工厂。
        """
        super().__init__(nodes, size)
        if isinstance(density, int):
            # GeoCell 每个地理单元内生成多少子节点的随机采样器。
            self.density = ConstantSampler(density)
        elif isinstance(density, RandomSampler):
            self.density = IntegerTruncationSampler(density)
        else:
            raise ValueError('unknown density type %s' % type(density))

    def materialize(self, topology: Topology, parent=None):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。
        - parent：当前 Cell 的父级网络单元，主要用于递归物化时保留层级关系。

        """
        for i in range(self.size):
            n = self.density.sample()

            for c in self.nodes:
                if callable(c):
                    sig: inspect.Signature = inspect.signature(c)
                    # 根据工厂函数签名决定是否传入密度采样值，后续可扩展更完整参数传递。
                    if len(sig.parameters) > 0:
                        c = c(n)
                    else:
                        # 节点或子单元工厂在物化阶段被调用，生成真实 Host/Cell 对象。
                        c = c()
                # 递归展开生成的子单元，把内部节点和链路加入拓扑图。
                self._materialize(topology, c)
