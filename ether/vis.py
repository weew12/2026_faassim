"""Ether 拓扑可视化辅助文件，根据节点类型为 networkx 拓扑生成颜色映射，便于快速查看网络结构。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【工具层】—— NetworkX 静态拓扑可视化。

提供:
    - draw_basic: 4 类节点分色 (Node / Link / switch_ 字符串 / internet 字符串)
    - kamada_kawai_layout: 力导向布局 (适合网络拓扑)
    - matplotlib 静态图 (不是交互式)

设计哲学:
    1. 简单、快速、依赖少 (只 networkx + matplotlib)
    2. 节点按类型分色, 一眼能看出网络结构
    3. 适合"开发期调试"和"论文 publication-quality 图"

对 CSAC 论文的接口:
    - 论文主图(高 dpi): plt.savefig('fig.pdf', dpi=300)
    - 如果要交互式 HTML (补充材料),用 converter/pyvis.py
================================================================================
"""

import networkx as nx

from ether.core import Node, Link


def draw_basic(topology):
    """
    用 NetworkX 画一张静态拓扑图,4 类节点分色:
        蓝色 = 主机 (Node)
        绿色 = 链路 (Link)
        黄色 = 透明交换机 (以 switch_ 开头的字符串)
        红色 = 互联网节点 (以 internet 开头的字符串)

    参数：
    - topology：需要写入节点、链路和连接的 Ether 拓扑图。

    ─────────────────────────────────────────────────────────────
    【设计意图】为什么用 kamada_kawai_layout?
    ─────────────────────────────────────────────────────────────
    kamada_kawai 是基于"弹簧模型"的力导向布局:
      - 节点之间按距离有吸引力
      - 节点之间有排斥力防止重叠
      - 最终平衡状态呈现"网络结构"

    适合: 网络拓扑 (节点有连接关系)
    不适合: 纯随机点云 (没有边约束)
    替代: spring_layout, circular_layout (各有所长)

    论文图建议:
      import matplotlib.pyplot as plt
      fig, ax = plt.subplots(figsize=(12, 8))
      draw_basic(topology)
      plt.savefig('fig.pdf', bbox_inches='tight', dpi=300)
    ─────────────────────────────────────────────────────────────
    """
    pos = nx.kamada_kawai_layout(topology)  # positions for all nodes

    # nodes

    hosts = [node for node in topology.nodes if isinstance(node, Node)]
    links = [node for node in topology.nodes if isinstance(node, Link)]
    switches = [node for node in topology.nodes if str(node).startswith('switch_')]

    nx.draw_networkx_nodes(topology, pos,
                           nodelist=hosts,
                           node_color='b',
                           node_size=300,
                           alpha=0.8)
    nx.draw_networkx_nodes(topology, pos,
                           nodelist=links,
                           node_color='g',
                           node_size=50,
                           alpha=0.9)
    nx.draw_networkx_nodes(topology, pos,
                           nodelist=switches,
                           node_color='y',
                           node_size=200,
                           alpha=0.8)
    nx.draw_networkx_nodes(topology, pos,
                           nodelist=[node for node in topology.nodes if
                                     isinstance(node, str) and node.startswith('internet')],
                           node_color='r',
                           node_size=800,
                           alpha=0.8)

    nx.draw_networkx_edges(topology, pos, width=1.0, alpha=0.5)
    nx.draw_networkx_labels(topology, pos, dict(zip(hosts, hosts)), font_size=10)
    nx.draw_networkx_labels(topology, pos, dict(zip(links, [l.tags['type'] for l in links])), font_size=8)
    # nx.draw_networkx_labels(topology, pos, dict(zip(links, links)), font_size=8)
