"""
文件作用：拓扑检查与路由信息提取工具。

不同版本的 Ether / faas-sim 对拓扑内部 NetworkX 图的封装字段可能略有差异。
因此本文件采用兼容式检查方法，尽量通过公开属性或常见字段读取图结构。
"""

from typing import Any, Dict, List, Optional

import pandas as pd
from ether.core import Link, Node


def link_name(link: Link) -> str:
    """
    返回链路名称。
    """
    return link.tags.get("name", str(link))


def safe_name(obj: Any) -> str:
    """
    返回节点或链路的可读名称。
    """
    if hasattr(obj, "name"):
        return str(obj.name)

    if isinstance(obj, Link):
        return link_name(obj)

    return str(obj)


def get_graph(topology) -> Optional[Any]:
    """
    从 Topology 对象中获取底层图对象。

    常见字段包括：
    - topology.g
    - topology.graph
    - topology.network
    - topology._graph
    """
    for attr in ["g", "graph", "network", "_graph"]:
        value = getattr(topology, attr, None)
        if value is not None and hasattr(value, "nodes") and hasattr(value, "edges"):
            return value

    return None


def collect_graph_nodes(topology_case) -> pd.DataFrame:
    """
    收集拓扑图中的节点信息。

    如果无法读取底层图，则回退到样例中显式创建的 nodes / links。
    """
    graph = get_graph(topology_case.topology)
    rows: List[Dict[str, Any]] = []

    if graph is not None:
        for item in graph.nodes:
            node_type = "link" if isinstance(item, Link) else "node"
            if not isinstance(item, (Node, Link)) and isinstance(item, str):
                node_type = "switch"

            rows.append({
                "topology": topology_case.name,
                "name": safe_name(item),
                "object_type": node_type,
                "arch": getattr(item, "arch", None),
                "bandwidth": getattr(item, "bandwidth", None),
                "tags": getattr(item, "tags", None),
            })

        return pd.DataFrame(rows)

    for name, node in topology_case.nodes.items():
        rows.append({
            "topology": topology_case.name,
            "name": name,
            "object_type": "node",
            "arch": getattr(node, "arch", None),
            "bandwidth": None,
            "tags": None,
        })

    for name, link in topology_case.links.items():
        rows.append({
            "topology": topology_case.name,
            "name": name,
            "object_type": "link",
            "arch": None,
            "bandwidth": getattr(link, "bandwidth", None),
            "tags": getattr(link, "tags", None),
        })

    return pd.DataFrame(rows)


def collect_graph_edges(topology_case) -> pd.DataFrame:
    """
    收集拓扑图中的边信息。
    """
    graph = get_graph(topology_case.topology)
    rows: List[Dict[str, Any]] = []

    if graph is None:
        return pd.DataFrame(rows)

    for source, target, data in graph.edges(data=True):
        row = {
            "topology": topology_case.name,
            "source": safe_name(source),
            "target": safe_name(target),
        }

        if isinstance(data, dict):
            for key, value in data.items():
                row[key] = value

        rows.append(row)

    return pd.DataFrame(rows)


def collect_route_records(topology_case) -> pd.DataFrame:
    """
    收集样例节点之间的路由信息。

    对每个显式业务节点，尝试计算到最后一个业务节点的 route。
    对 urban_sensing 这类未显式记录 nodes 的复杂拓扑，只输出空表。
    """
    node_items = list(topology_case.nodes.items())

    if len(node_items) < 2:
        return pd.DataFrame()

    sink_name, sink_node = node_items[-1]
    rows: List[Dict[str, Any]] = []

    for source_name, source_node in node_items[:-1]:
        try:
            route = topology_case.topology.route(source_node, sink_node)
        except Exception as err:
            rows.append({
                "topology": topology_case.name,
                "source": source_name,
                "sink": sink_name,
                "route_available": False,
                "error": str(err),
            })
            continue

        bottleneck = min(route.hops, key=lambda item: item.bandwidth) if route.hops else None

        rows.append({
            "topology": topology_case.name,
            "source": source_name,
            "sink": sink_name,
            "route_available": True,
            "rtt_ms": route.rtt,
            "hop_count": len(route.hops),
            "path": " -> ".join([safe_name(item) for item in route.path]),
            "hops": " -> ".join([link_name(link) for link in route.hops]),
            "bottleneck_link": link_name(bottleneck) if bottleneck is not None else None,
            "bottleneck_bandwidth_mbps": bottleneck.bandwidth if bottleneck is not None else None,
        })

    return pd.DataFrame(rows)


def build_topology_summary(topology_case, node_df: pd.DataFrame, edge_df: pd.DataFrame, route_df: pd.DataFrame) -> Dict[str, Any]:
    """
    生成单个拓扑的摘要记录。
    """
    explicit_node_count = len(topology_case.nodes)
    explicit_link_count = len(topology_case.links)

    graph_node_count = len(node_df) if node_df is not None else 0
    graph_edge_count = len(edge_df) if edge_df is not None else 0

    return {
        "topology": topology_case.name,
        "description": topology_case.description,
        "explicit_node_count": explicit_node_count,
        "explicit_link_count": explicit_link_count,
        "graph_node_count": graph_node_count,
        "graph_edge_count": graph_edge_count,
        "route_records": len(route_df) if route_df is not None else 0,
    }
