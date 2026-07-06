"""Ether 拓扑导出文件，将拓扑节点和边转换为 JSON 结构，便于外部工具展示或持久化网络图。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【工具层】—— 拓扑数据导出器。

提供:
    - export_to_tam_json: Topology → TAM 格式 JSON
    - 节点按类型分类处理 (Node 实例 / Link 实例 / 字符串)
    - 支持用户自定义 value_projector 把节点映射成数值
      (供外部工具如 Gephi / D3.js / Cytoscape 按值着色)

输出格式:
    {
      "nodes": [
        {"id": ..., "name": ..., "value": ...},
        ...
      ],
      "links": [
        {"source": ..., "target": ..., "directed": ...},
        ...
      ]
    }
    节点 id / 边 source-target 都用 Python id() (内存地址),保证唯一

对 CSAC 论文的接口:
    - 实验数据导出 (供 Gephi / Cytoscape 画图)
    - value_projector: 按节点 CPU 利用率 / 内存使用 / 任务数等映射数值
================================================================================
"""

from typing import Callable
from ether.topology import Topology
from ether.core import Node
import json


def export_to_tam_json(topology: Topology, output_file: str, value_projector: Callable[[Node], int]):
    """
    把 Topology 导出为 TAM 格式 JSON,供 Gephi / D3.js / Cytoscape 等工具打开。

    参数：
    - topology：需要写入节点、链路和连接的 Ether 拓扑图。
    - output_file: 输出文件路径
    - value_projector: 用户自定义函数,把节点映射成数值 (供外部工具按值着色)

    ─────────────────────────────────────────────────────────────
    【设计意图】节点分类处理 + 边统一格式
    ─────────────────────────────────────────────────────────────
    节点处理 (3 类):
      1) 字符串 (透明链路 / internet 节点): name = 字符串本身, value = 0
      2) Node 实例:                        name = node.name,       value = value_projector(node)
      3) Link 实例:                        name = link.tags['name'],value = value_projector(node)

    边处理: 每条 Connection 转成
      {"source": id(source), "target": id(target), "directed": edge['directed']}
      id() 用 Python 内存地址,保证全图唯一

    使用方式:
      def cpu_value(node): return node.capacity.cpu_millis
      export_to_tam_json(t, 'out.json', cpu_value)
    然后用 Gephi 打开 out.json,按 value 字段着色
    ─────────────────────────────────────────────────────────────
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
