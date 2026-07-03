"""
文件作用：Ether 拓扑包装层，提供容器仓库节点初始化、节点查找、路由查询和按需带宽图访问。
主要类：Topology、LazyBandwidthGraph。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

from collections import defaultdict
from typing import Optional

import ether.topology
from ether.core import Node, Connection

# 字段说明：DockerRegistry：表示 docker、registry，在当前业务流程中作为输入参数、状态字段或计算结果使用。
DockerRegistry = Node('registry')


class Topology(ether.topology.Topology):

    """
    类作用：Ether 拓扑封装，持有节点/链路图并提供容器仓库、路由和节点查找能力。
    继承关系：ether.topology.Topology。
    核心方法：__init__、init_docker_registry、route_by_node_name、find_node。
    """
    def __init__(self, incoming_graph_data=None, **attr):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：_node_index。
        参数：incoming_graph_data：表示 incoming、graph、data，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__(incoming_graph_data, **attr)
        # 字段说明：self._node_index：索引表，用于按名称快速查找对象。
        self._node_index = dict()

    def init_docker_registry(self):
        """
        函数作用：把容器仓库作为拓扑中的特殊节点加入网络。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if DockerRegistry not in self.nodes:
            self.add_node(DockerRegistry)
        for node in self.nodes:
            if isinstance(node, str) and node.startswith('internet'):
                self.add_connection(Connection(node, DockerRegistry))

    def route_by_node_name(self, source_name: str, destination_name: str):
        """
        函数作用：根据节点名称查询两点之间的网络路径。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：source_name：表示 source、name，在当前业务流程中作为输入参数、状态字段或计算结果使用。；destination_name：表示 destination、name，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        source = self.find_node(source_name)
        if source is None:
            raise ValueError('source node not found: ' + source_name)

        destination = self.find_node(destination_name)
        if destination is None:
            raise ValueError('destination node not found: ' + destination_name)

        return self.route(source, destination)

    def find_node(self, node_name: str) -> Optional[Node]:
        """
        函数作用：按节点名称在拓扑中查找 Ether 节点对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if node_name in self._node_index:
            return self._node_index[node_name]

        for node in self.get_nodes():
            if node.name == node_name:
                self._node_index[node_name] = node
                return node

        return None


class LazyBandwidthGraph:
    """
    类作用：按需带宽图代理，在调度器访问两个节点时临时查询 Ether 路由带宽。
    核心字段：topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。。
    核心方法：__init__、__getitem__。
    """
    # 字段说明：topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
    topology: Topology

    def __init__(self, topology: Topology) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：cache、topology。
        参数：topology：Ether 网络拓扑。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.cache：缓存表，避免重复构造昂贵对象或重复计算调度/网络结果。
        self.cache = defaultdict(dict)
        # 字段说明：self.topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
        self.topology = topology

    def __getitem__(self, source):
        """
        函数作用：按键读取内部字段或资源项。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：source：源节点或源数据对象，用于网络传输和拓扑构造。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._Resolver(self, source)

    class _Resolver:
        """
        类作用：_Resolver 类，封装 resolver 相关状态和业务操作。
        核心方法：__init__、__getitem__。
        """
        def __init__(self, bwg: 'LazyBandwidthGraph', source: str) -> None:
            """
            函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
            关键流程：
            - 写入对象字段：bwg、source。
            参数：bwg：带宽图对象，描述节点间可用带宽。；source：源节点或源数据对象，用于网络传输和拓扑构造。。
            返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
            """
            super().__init__()
            # 字段说明：self.bwg：带宽图对象，描述节点间可用带宽。
            self.bwg = bwg
            # 字段说明：self.source：源节点或源数据对象，用于网络传输和拓扑构造。
            self.source = source

        def __getitem__(self, destination: str) -> Optional[float]:
            """
            函数作用：按键读取内部字段或资源项。
            关键流程：
            - 返回计算结果或被创建的业务对象，供上层流程继续使用。
            参数：destination：表示 destination，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
            返回：与该业务步骤对应的对象、指标或计算结果。
            """
            if destination in self.bwg.cache[self.source]:
                return self.bwg.cache[self.source][destination]

            if self.source == destination:
                # 修正提示：这里标记了原实现中需要进一步确认的边界。
                return 1.25e+8

            route = self.bwg.topology.route_by_node_name(self.source, destination)
            if not route or not route.hops:
                return None

            bandwidth = min([link.bandwidth for link in route.hops])

            self.bwg.cache[self.source][destination] = bandwidth
            return bandwidth
