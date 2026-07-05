"""
文件作用：构造 data_locality 样例使用的自定义边缘-存储拓扑。

拓扑中包含三个计算节点和一个存储节点：
- edge_near：靠近 storage_near；
- edge_mid：中等距离；
- edge_far：远离 storage_near；
- storage_near：对象数据所在的存储节点。

该拓扑用于稳定观察数据本地性对调度与数据下载时间的影响。
"""

from dataclasses import dataclass
from typing import Dict

from ether.core import Node, Link, Connection, Capacity
from sim.topology import Topology


@dataclass
class DataLocalityTopology:
    """
    数据本地性拓扑封装。
    """

    topology: Topology
    nodes: Dict[str, Node]
    links: Dict[str, Link]


def build_data_locality_topology() -> DataLocalityTopology:
    """
    构造数据本地性样例拓扑。

    拓扑结构：

    ```text
                         storage_near
                              |
                        storage_link
                              |
    edge_near -- near_link -- data_switch -- mid_link -- edge_mid
                              |
                            far_link
                              |
                           edge_far

    internet -- internet_link -- data_switch
    DockerRegistry 会由 topology.init_docker_registry() 自动连接到 internet。
    ```

    说明：
    - storage_near 使用 `data.skippy.io/storage` 标签标记为存储节点；
    - Skippy 默认谓词会避免普通函数直接调度到存储节点；
    - DataLocalityPriority 会倾向选择距离 storage_near 更近、带宽更高的计算节点。
    """
    topology = Topology()

    capacity = Capacity(cpu_millis=2000, memory=2 * 1024 * 1024 * 1024)

    nodes = {
        "edge_near": Node(
            "edge_near",
            capacity=capacity,
            arch="x86",
            labels={"ether.edgerun.io/type": "edge", "zone": "near"},
        ),
        "edge_mid": Node(
            "edge_mid",
            capacity=capacity,
            arch="x86",
            labels={"ether.edgerun.io/type": "edge", "zone": "mid"},
        ),
        "edge_far": Node(
            "edge_far",
            capacity=capacity,
            arch="x86",
            labels={"ether.edgerun.io/type": "edge", "zone": "far"},
        ),
        "storage_near": Node(
            "storage_near",
            capacity=capacity,
            arch="x86",
            labels={"data.skippy.io/storage": "true", "zone": "near"},
        ),
    }

    links = {
        "near_link": Link(bandwidth=200, tags={"name": "near_link", "type": "near_data_path"}),
        "mid_link": Link(bandwidth=60, tags={"name": "mid_link", "type": "mid_data_path"}),
        "far_link": Link(bandwidth=10, tags={"name": "far_link", "type": "far_data_path"}),
        "storage_link": Link(bandwidth=200, tags={"name": "storage_link", "type": "storage_access"}),
        "internet_link": Link(bandwidth=100, tags={"name": "internet_link", "type": "registry_access"}),
    }

    data_switch = "data_switch"
    internet = "internet"

    topology.add_connection(Connection(nodes["edge_near"], links["near_link"], latency=2))
    topology.add_connection(Connection(links["near_link"], data_switch, latency=1))

    topology.add_connection(Connection(nodes["edge_mid"], links["mid_link"], latency=8))
    topology.add_connection(Connection(links["mid_link"], data_switch, latency=2))

    topology.add_connection(Connection(nodes["edge_far"], links["far_link"], latency=25))
    topology.add_connection(Connection(links["far_link"], data_switch, latency=5))

    topology.add_connection(Connection(nodes["storage_near"], links["storage_link"], latency=1))
    topology.add_connection(Connection(links["storage_link"], data_switch, latency=1))

    topology.add_connection(Connection(internet, links["internet_link"], latency=5))
    topology.add_connection(Connection(links["internet_link"], data_switch, latency=5))

    topology.init_docker_registry()

    return DataLocalityTopology(
        topology=topology,
        nodes=nodes,
        links=links,
    )
