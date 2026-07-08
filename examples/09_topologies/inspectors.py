"""
文件作用：拓扑检查与路由信息提取工具。

不同版本的 Ether / faas-sim 对拓扑内部 NetworkX 图的封装字段可能略有差异。
本文件采用兼容式检查方法：faas-sim 的 Topology 本身就是 networkx.DiGraph 子类，
可以直接作为图遍历使用。
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


def get_graph(topology):
    """
    从 Topology 对象中获取底层图对象。

    faas-sim 的 `Topology` 本身就是 networkx.DiGraph 的子类（拥有 .nodes()/.edges()/.add_edge()），
    不需要从 g/graph/network/_graph 子字段里找。
    直接返回 topology 本身即可。

    返回：图对象（NetworkX DiGraph 或兼容接口）。
    返回空：当 topology 为 None 或者完全没有图能力时。
    """
    if topology is None:
        return None
    if hasattr(topology, "nodes") and hasattr(topology, "edges") and callable(getattr(topology, "edges", None)):
        return topology
    return None


def collect_graph_nodes(topology_case) -> pd.DataFrame:
    """
    收集拓扑图中的节点信息。

    优先从底层图（Topology 本身）读取节点；
    如果读取不到，回退到样例中显式创建的 nodes / links（仅适用于手工小拓扑）。
    """
    graph = get_graph(topology_case.topology)
    rows: List[Dict[str, Any]] = []

    if graph is not None:
        # NetworkX 的 DiGraph.nodes 是 NodeView，直接 for 迭代
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

    # Fallback: 手工拓扑 case 里 nodes/links 字典
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
    收集拓扑图中的边信息（含 connection.latency / directed 等 metadata）。

    faas-sim 的 Topology 是个有向图；调用 add_connection 实际上会插入双向边，
    所以一条物理连接会产生 2 行（a→link 和 link→a）。
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
                # Connection 对象不能直接 csv 化，单独保留 latency 字段
                if key == "connection" and value is not None:
                    row["latency"] = getattr(value, "latency", None)
                    row["connection_source"] = safe_name(getattr(value, "source", None))
                    row["connection_target"] = safe_name(getattr(value, "target", None))
                else:
                    row[key] = value

        rows.append(row)

    return pd.DataFrame(rows)


def collect_route_records(topology_case) -> pd.DataFrame:
    """
    收集样例节点之间的路由信息。

    优先用样例显式业务节点（case.nodes）作为 source/sink；
    对于 urban_sensing 这类没有 case.nodes 的复杂拓扑，回退到 graph 中
    按 name 排序的前若干个 Node + 最后一个 Node。
    """
    rows: List[Dict[str, Any]] = []
    topology = topology_case.topology

    # 1) 优先使用 case.nodes（手工小拓扑）
    node_items = list(topology_case.nodes.items())
    use_graph_fallback = len(node_items) < 2

    sources = []
    if not use_graph_fallback:
        # 手写拓扑优先把 cloud 节点作为 sink，避免由字典插入顺序决定路由方向。
        sink_name, sink_node = node_items[-1]
        for candidate_name, candidate_node in node_items:
            readable_name = safe_name(candidate_node).lower()
            if "cloud" in candidate_name.lower() or "cloud" in readable_name:
                sink_name, sink_node = candidate_name, candidate_node
                break

        for source_name, source_node in node_items:
            if source_node is sink_node:
                continue
            sources.append((source_name, source_node))

    # 2) Fallback：对于 urban_sensing，从 graph 里挑名字像 server_xxx / switch_lan_xx 等
    #    关键节点作 source/sink
    if use_graph_fallback:
        graph_nodes = [n for n in topology.nodes() if isinstance(n, Node)]
        if len(graph_nodes) < 2:
            return pd.DataFrame()

        graph_nodes_sorted = sorted(graph_nodes, key=lambda n: str(getattr(n, "name", "")))

        # 选 sink：名字含 "cloudlet" 或 "cloud" 优先；否则最后一个
        sink_node = None
        for n in graph_nodes_sorted:
            name = str(getattr(n, "name", ""))
            if "cloudlet" in name or "cloud" in name:
                sink_node = n
                break
        if sink_node is None:
            sink_node = graph_nodes_sorted[-1]
        sink_name = safe_name(sink_node)

        # 选 sources：每个 SharedLinkCell / Neighborhood 选 1 个代表节点
        #    简单做法：取所有 node，按名字前缀去重
        seen_prefixes = set()
        for n in graph_nodes_sorted:
            if n is sink_node:
                continue
            name = str(getattr(n, "name", ""))
            prefix = name.split("_")[0] if "_" in name else name
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)
            sources.append((safe_name(n), n))
            if len(sources) >= 4:
                break

    for source_name, source_node in sources:
        try:
            route = topology.route(source_node, sink_node)
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
