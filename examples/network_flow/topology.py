"""
文件作用：构造 network_flow 样例使用的网络拓扑。

该拓扑刻意构造一个边缘到云端的瓶颈链路，用于观察：
- 单个 Flow 的传输耗时；
- 多个 Flow 共享同一链路时的竞争关系；
- 带宽、RTT 和数据大小对网络传输时间的影响。
"""

from dataclasses import dataclass
from typing import Dict

from ether.core import Node, Link, Connection
from sim.topology import Topology


@dataclass
class NetworkFlowTopology:
    """
    网络流样例拓扑封装。

    字段：
    - topology：Ether / faas-sim 拓扑对象；
    - nodes：业务节点索引；
    - links：链路对象索引。
    """

    topology: Topology
    nodes: Dict[str, Node]
    links: Dict[str, Link]


def build_network_flow_topology() -> NetworkFlowTopology:
    """
    构造一个包含共享瓶颈链路的网络拓扑。

    拓扑结构：

    ```text
    edge_client_a -- access_a -- edge_switch -- bottleneck -- core_switch -- cloud_server
    edge_client_b -- access_b --/
    edge_client_c -- access_c --/
    ```

    说明：
    - edge_client_a / b / c 表示边缘侧请求源；
    - cloud_server 表示云端或远端服务节点；
    - access_a / b / c 是接入链路，带宽较高；
    - bottleneck 是共享瓶颈链路，带宽较低；
    - 多个 Flow 同时经过 bottleneck 时，会触发 Ether 的链路带宽共享逻辑。

    返回：
    - NetworkFlowTopology：包含拓扑、节点和链路索引。
    """
    topology = Topology()

    nodes = {
        "edge_client_a": Node("edge_client_a", arch="x86"),
        "edge_client_b": Node("edge_client_b", arch="x86"),
        "edge_client_c": Node("edge_client_c", arch="x86"),
        "cloud_server": Node("cloud_server", arch="x86"),
    }

    links = {
        "access_a": Link(bandwidth=100, tags={"name": "access_a", "type": "access"}),
        "access_b": Link(bandwidth=100, tags={"name": "access_b", "type": "access"}),
        "access_c": Link(bandwidth=100, tags={"name": "access_c", "type": "access"}),
        "bottleneck": Link(bandwidth=10, tags={"name": "bottleneck", "type": "shared_bottleneck"}),
        "cloud_access": Link(bandwidth=80, tags={"name": "cloud_access", "type": "cloud_access"}),
    }

    edge_switch = "edge_switch"
    core_switch = "core_switch"

    connections = [
        Connection(nodes["edge_client_a"], links["access_a"], latency=2),
        Connection(links["access_a"], edge_switch, latency=1),

        Connection(nodes["edge_client_b"], links["access_b"], latency=2),
        Connection(links["access_b"], edge_switch, latency=1),

        Connection(nodes["edge_client_c"], links["access_c"], latency=2),
        Connection(links["access_c"], edge_switch, latency=1),

        Connection(edge_switch, links["bottleneck"], latency=10),
        Connection(links["bottleneck"], core_switch, latency=20),

        Connection(core_switch, links["cloud_access"], latency=5),
        Connection(links["cloud_access"], nodes["cloud_server"], latency=2),
    ]

    for connection in connections:
        topology.add_connection(connection)

    return NetworkFlowTopology(topology=topology, nodes=nodes, links=links)
