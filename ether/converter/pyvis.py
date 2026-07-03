"""PyVis 转换文件，把 Ether 拓扑中的节点、链路和连接转换为 PyVis Network，可生成交互式 HTML 网络图。"""

from pyvis.network import Network

from ether.core import Link, Node, Connection
from ether.topology import Topology


def topology_to_pyvis(topology: Topology) -> Network:
    """
    topology_to_pyvis 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    参数：
    - topology：需要写入节点、链路和连接的 Ether 拓扑图。

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
