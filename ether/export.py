"""Ether 拓扑导出文件，将拓扑节点和边转换为 JSON 结构，便于外部工具展示或持久化网络图。"""

from typing import Callable
from ether.topology import Topology
from ether.core import Node
import json


def export_to_tam_json(topology: Topology, output_file: str, value_projector: Callable[[Node], int]):
    """
    export_to_tam_json 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    参数：
    - topology：需要写入节点、链路和连接的 Ether 拓扑图。

    """
    nodes = []
    links = []
    if value_projector is None:
        value_projector = lambda: 0
    for node in topology.nodes:
        if isinstance(node, str):
            nodes.append({
                'id': id(node),
                'name': node,
                'value': 0
            })
            continue
        nodes.append({
            'id': id(node),
            'name': node.name if isinstance(node, Node) else node.tags['name'],
            'value': value_projector(node)
        })
    for edge in topology.edges.values():
        links.append({
            'source': id(edge['connection'].source),
            'target': id(edge['connection'].target),
            'directed': edge['directed']
        })
    full = {
        'nodes': nodes,
        'links': links
    }
    with open(output_file, 'w') as file:
        json.dump(full, file)
        file.flush()
        file.close()
