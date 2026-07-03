"""Ether 拓扑图实现文件，在 networkx 有向图基础上封装连接添加、最短路径路由、RTT 计算、互联网延迟图加载和场景物化能力。"""

import abc
import logging
from copy import copy
from typing import Dict, Tuple

import networkx as nx

from ether.core import Node, Link, Connection, Route, NetworkNode
from ether.inet.graph import load_latest

logger = logging.getLogger(__name__)


class Template(abc.ABC):
    """可物化拓扑模板抽象，约束场景或网络单元把自身展开到 Topology 中。"""
    def materialize(self, topology: 'Topology'):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。

        """
        ...


class Topology(nx.DiGraph):

    """Ether 拓扑图对象，继承 networkx.DiGraph，负责保存节点/链路/连接并提供路由、时延和场景添加能力。"""
    def __init__(self, incoming_graph_data=None, **attr):
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。
        """
        super().__init__(incoming_graph_data, **attr)
        # 源节点到目标节点的路由缓存，避免重复执行最短路径计算。
        self._route_cache: Dict[Tuple[NetworkNode, NetworkNode], Route] = dict()

    def conn(self, *args, **kwargs):
        """
        add_connection 的简写接口，用于向拓扑中加入一条连接。

        """
        return self.add_connection(*args, **kwargs)

    def add_connection(self, connection: Connection, directed=False):
        """
        把 Connection 添加为拓扑边；无向连接会自动添加反向边。

        参数：
        - directed：是否只添加单向边；为 False 时自动添加反向连接。

        """
        if isinstance(connection.source, Node) and isinstance(connection.target, Node):
            raise ValueError('Cannot have direct Node-to-Node connections')

        self.add_edge(connection.source, connection.target, directed=directed, connection=connection)
        if directed is False:
            self.add_edge(connection.target, connection.source, directed=directed, connection=connection)

    def path(self, source, destination):
        """
        使用 networkx 最短路径算法返回两个顶点之间的路径。

        参数：
        - source：路由、连接或测量数据的源端。
        - destination：路由或网络流传输的目标节点。

        返回： networkx 计算得到的最短路径顶点列表。

        """
        return nx.shortest_path(self, source, destination)

    def latency(self, source: Node, destination: Node, use_coordinates=False) -> float:
        """
        查询两个节点之间的单向时延，可选择直接使用坐标距离或路由 RTT。

        参数：
        - source：路由、连接或测量数据的源端。
        - destination：路由或网络流传输的目标节点。
        - use_coordinates：是否直接使用节点坐标距离估计时延。

        返回：源节点到目标节点的单向时延。

        """
        if use_coordinates:
            return source.distance_to(destination)
        return self.route(source, destination).rtt / 2

    def route(self, source, destination, use_mode: bool = False) -> Route:
        """
        返回源节点到目标节点的 Route；首次查询时解析路径并缓存，后续按需刷新随机 RTT。

        参数：
        - source：路由、连接或测量数据的源端。
        - destination：路由或网络流传输的目标节点。
        - use_mode：是否使用时延分布众数；用于缓存路由时避免随机采样扰动。

        返回：源节点到目标节点的 Route。

        """
        k = (source, destination)

        if k not in self._route_cache:
            # 首次查询时解析最短路径并写入缓存，降低重复路由计算开销。
            self._route_cache[k] = self._resolve_route(source, destination)

        if not use_mode:
            route = copy(self._route_cache[k])
            # 每次实际使用路由前重新采样随机时延，使同一路径也能体现网络波动。
            self._update_rtt(route)
        else:
            route = self._route_cache[k]

        return route

    def get_nodes(self):
        """
        返回拓扑中所有计算/存储 Node 顶点。

        返回：拓扑中所有 Node 对象。

        """
        return [n for n in self.nodes if isinstance(n, Node)]

    def get_links(self):
        """
        返回拓扑中所有 Link 顶点。

        返回：拓扑中所有 Link 对象。

        """
        return [n for n in self.nodes if isinstance(n, Link)]

    def load_inet_graph(self, source):
        """
        把预置互联网区域延迟图加载到当前拓扑中。

        参数：
        - source：路由、连接或测量数据的源端。

        """
        load_latest(self, source)

    def _resolve_route(self, source, destination) -> Route:
        """
        计算并缓存两个节点之间的最短路径路由。

        参数：
        - source：路由、连接或测量数据的源端。
        - destination：路由或网络流传输的目标节点。

        """
        # 最短路径解析得到的完整拓扑顶点序列。
        path = self.path(source, destination)
        # 本次网络流使用的端到端路由。
        route = Route(source, destination, path=path)
        self._update_rtt(route, use_mode=True)
        return route

    def _update_rtt(self, route: Route, use_mode: bool = False):
        """
        沿路由路径累加连接时延并更新双向 RTT。

        参数：
        - route：网络流使用的端到端路由。
        - use_mode：是否使用时延分布众数；用于缓存路由时避免随机采样扰动。

        """
        # 固定单向链路时延。
        latency: float = 0
        for i in range(len(route.path)-1):
            edge_data = self.get_edge_data(route.path[i], route.path[i + 1])
            if 'connection' in edge_data and isinstance(edge_data['connection'], Connection):
                # 该边挂载了 Connection 对象，可从对象中读取固定或随机时延。
                # 根据是否需要稳定路由缓存，选择采样时延或分布众数时延。
                connection: Connection = edge_data['connection']
                latency += connection.get_mode_latency() if use_mode else connection.get_latency()
            elif 'latency' in edge_data:
                # 互联网 graphml 数据中的边通常直接保存固定 latency 属性。
                latency += edge_data['latency']
        route.rtt = latency * 2

    def add(self, cell):
        """
        将 Cell 或 Scenario 物化进拓扑，并返回自身以支持链式调用。

        参数：
        - cell：需要物化进拓扑的 Cell 或 Scenario 对象。

        返回：当前 Topology，支持链式调用。

        """
        cell.materialize(self)
        return self
