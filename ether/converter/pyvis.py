"""PyVis 转换文件，把 Ether 拓扑中的节点、链路和连接转换为 PyVis Network，可生成交互式 HTML 网络图。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【转换层】—— Topology → PyVis Network (HTML) 转换器。

用法:
    from ether.converter.pyvis import topology_to_pyvis
    net = topology_to_pyvis(topology)
    net.show('topology.html')              # 浏览器打开
    net.save_graph('topology.html')        # 保存

节点分类处理:
    Link         → 椭圆, 标签 'Link'
    Node(client) → 矩形, 绿边框
    Node(broker) → 矩形, 红边框
    Node(其他)   → 矩形, 默认边框
    字符串(透明/internet) → 矩形, 黑边框

边处理:
    双源 RTT (Connection.get_mode_latency() / data['latency'])
    latency > 0 → 红色边 + 标签 (如 "227.4")
    否则        → 普通边

对 CSAC 论文的接口:
    - 论文补充材料: 可交互 HTML (读者可点开看拓扑)
    - 演示视频: HTML 录屏
    - 答辩 PPT: HTML 演示给评委看拓扑结构
================================================================================
"""

from pyvis.network import Network

from ether.core import Link, Node, Connection
from ether.topology import Topology


def topology_to_pyvis(topology: Topology) -> Network:
    """
    把 Ether Topology 转换为 PyVis Network 对象,可生成交互式 HTML 网络图。

    参数：
    - topology: Ether 拓扑图

    返回：
    - pyvis.Network 对象,可调用 .show() / .save_graph() 生成 HTML
    """
    net = Network(height='90%', width='100%', heading='Urban Sensing')
    for node in topology.nodes:
        if isinstance(node, Link):
            net.add_node(str(node), label='Link', shape='ellipse')
        elif isinstance(node, Node):
            color = {'background': '#fff'}
            if 'client' in node.name:
                color['border'] = 'green'
            elif 'broker' in node.name:
                color['border'] = 'red'
            net.add_node(str(node), label=node.name, shape='box', color=color)
        else:
            net.add_node(str(node), label=str(node), shape='box', color={'border': '#000', 'background': '#fff'})

    for edge in topology.edges:
        data = topology[edge[0]][edge[1]]
        latency = 0
        if 'connection' in data and isinstance(data['connection'], Connection):
            latency = data['connection'].get_mode_latency()
        elif 'latency' in data:
            latency = data['latency']
        if latency > 0:
            net.add_edge(str(edge[0]), str(edge[1]), label=f'{latency:.1f}', color='red')
        else:
            net.add_edge(str(edge[0]), str(edge[1]))

    return net
