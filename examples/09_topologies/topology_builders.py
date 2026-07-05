"""
文件作用：构造 topologies 样例使用的多种拓扑。

该文件尽量使用 Ether / faas-sim 中最基础的 Node、Link、Connection 和 Topology，
避免依赖复杂实验流程，便于理解拓扑对象的基本组成方式。
"""

from dataclasses import dataclass
from typing import Dict, List

import ether.scenarios.urbansensing as scenario
from ether.core import Node, Link, Connection
from sim.topology import Topology


@dataclass
class TopologyCase:
    """
    一个拓扑样例。

    字段：
    - name：拓扑名称；
    - description：拓扑说明；
    - topology：faas-sim / Ether 拓扑对象；
    - nodes：样例中显式创建的业务节点索引；
    - links：样例中显式创建的链路索引。
    """

    name: str
    description: str
    topology: Topology
    nodes: Dict[str, Node]
    links: Dict[str, Link]


def build_minimal_topology() -> TopologyCase:
    """
    构造最小二节点拓扑。

    拓扑结构：

    ```text
    edge_node -- direct_link -- cloud_node
    ```

    该拓扑用于说明 Ether 中 Node、Link 和 Connection 的最小组合。
    """
    topology = Topology()

    nodes = {
        "edge_node": Node("edge_node", arch="x86"),
        "cloud_node": Node("cloud_node", arch="x86"),
    }

    links = {
        "direct_link": Link(
            bandwidth=100,
            tags={
                "name": "direct_link",
                "type": "direct",
            },
        ),
    }

    topology.add_connection(Connection(nodes["edge_node"], links["direct_link"], latency=2))
    topology.add_connection(Connection(links["direct_link"], nodes["cloud_node"], latency=5))

    return TopologyCase(
        name="minimal",
        description="最小二节点拓扑：一个边缘节点通过一条链路连接一个云端节点。",
        topology=topology,
        nodes=nodes,
        links=links,
    )


def build_edge_cloud_star_topology(edge_count: int = 4) -> TopologyCase:
    """
    构造边缘-云星型拓扑。

    拓扑结构：

    ```text
    edge_0 -- access_0 -- edge_switch -- backbone -- cloud_switch -- cloud_node
    edge_1 -- access_1 --/
    edge_2 -- access_2 --/
    edge_3 -- access_3 --/
    ```

    该拓扑用于说明多个边缘节点共享一条云边骨干链路的建模方式。
    """
    topology = Topology()

    nodes: Dict[str, Node] = {
        "cloud_node": Node("cloud_node", arch="x86"),
    }

    links: Dict[str, Link] = {
        "backbone": Link(
            bandwidth=50,
            tags={
                "name": "backbone",
                "type": "cloud_edge_backbone",
            },
        ),
        "cloud_access": Link(
            bandwidth=200,
            tags={
                "name": "cloud_access",
                "type": "cloud_access",
            },
        ),
    }

    edge_switch = "edge_switch"
    cloud_switch = "cloud_switch"

    for index in range(edge_count):
        node_name = f"edge_{index}"
        link_name = f"access_{index}"

        nodes[node_name] = Node(node_name, arch="x86")
        links[link_name] = Link(
            bandwidth=100,
            tags={
                "name": link_name,
                "type": "edge_access",
            },
        )

        topology.add_connection(Connection(nodes[node_name], links[link_name], latency=2))
        topology.add_connection(Connection(links[link_name], edge_switch, latency=1))

    topology.add_connection(Connection(edge_switch, links["backbone"], latency=8))
    topology.add_connection(Connection(links["backbone"], cloud_switch, latency=20))
    topology.add_connection(Connection(cloud_switch, links["cloud_access"], latency=3))
    topology.add_connection(Connection(links["cloud_access"], nodes["cloud_node"], latency=2))

    return TopologyCase(
        name="edge_cloud_star",
        description="多个边缘节点经接入链路汇聚到云端，适合观察云边骨干链路共享。",
        topology=topology,
        nodes=nodes,
        links=links,
    )


def build_bottleneck_topology() -> TopologyCase:
    """
    构造带共享瓶颈链路的拓扑。

    该拓扑与 network_flow 样例中的思想一致，但规模更小，
    用于在拓扑样例中说明 bottleneck link 的建模方式。
    """
    topology = Topology()

    nodes = {
        "edge_a": Node("edge_a", arch="x86"),
        "edge_b": Node("edge_b", arch="x86"),
        "cloud_node": Node("cloud_node", arch="x86"),
    }

    links = {
        "edge_a_access": Link(
            bandwidth=100,
            tags={
                "name": "edge_a_access",
                "type": "access",
            },
        ),
        "edge_b_access": Link(
            bandwidth=100,
            tags={
                "name": "edge_b_access",
                "type": "access",
            },
        ),
        "bottleneck": Link(
            bandwidth=10,
            tags={
                "name": "bottleneck",
                "type": "shared_bottleneck",
            },
        ),
        "cloud_access": Link(
            bandwidth=80,
            tags={
                "name": "cloud_access",
                "type": "cloud_access",
            },
        ),
    }

    edge_switch = "edge_switch"
    cloud_switch = "cloud_switch"

    topology.add_connection(Connection(nodes["edge_a"], links["edge_a_access"], latency=2))
    topology.add_connection(Connection(links["edge_a_access"], edge_switch, latency=1))

    topology.add_connection(Connection(nodes["edge_b"], links["edge_b_access"], latency=2))
    topology.add_connection(Connection(links["edge_b_access"], edge_switch, latency=1))

    topology.add_connection(Connection(edge_switch, links["bottleneck"], latency=10))
    topology.add_connection(Connection(links["bottleneck"], cloud_switch, latency=20))

    topology.add_connection(Connection(cloud_switch, links["cloud_access"], latency=3))
    topology.add_connection(Connection(links["cloud_access"], nodes["cloud_node"], latency=2))

    return TopologyCase(
        name="bottleneck",
        description="两个边缘节点共享一条低带宽瓶颈链路连接云端。",
        topology=topology,
        nodes=nodes,
        links=links,
    )


def build_urban_sensing_topology() -> TopologyCase:
    """
    构造官方 UrbanSensingScenario 拓扑。

    该拓扑来自 Ether 官方场景，faas-sim 官方样例中也常使用该拓扑。
    它比手写拓扑更接近真实边缘网络，节点数量更多，适合后续复杂实验。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()

    return TopologyCase(
        name="urban_sensing",
        description="官方 UrbanSensingScenario 拓扑，包含较多边缘节点和网络连接。",
        topology=topology,
        nodes={},
        links={},
    )


def build_all_topology_cases() -> List[TopologyCase]:
    """
    构造所有拓扑样例。
    """
    return [
        build_minimal_topology(),
        build_edge_cloud_star_topology(edge_count=4),
        build_bottleneck_topology(),
        build_urban_sensing_topology(),
    ]
