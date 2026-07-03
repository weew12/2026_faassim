"""互联网延迟图处理文件，负责 graphml 文件路径管理、图保存、图加载以及把测量数据写入拓扑边。"""

import os
from typing import List

import networkx as nx

from ether.inet.fetch import Measurement

# 互联网延迟 graphml 文件所在目录。
graph_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), 'graphs'))


def load_latest(graph: nx.DiGraph, source, *args, **kwargs):
    """
    从本地 graphs 目录加载指定数据源的 latest graphml 延迟图。

    参数：
    - graph：networkx 图对象。
    - source：路由、连接或测量数据的源端。

    返回：加载完成的 networkx 图对象。

    """
    return load_tagged(graph, source, 'latest', *args, **kwargs)


def load_tagged(graph: nx.DiGraph, source, tag, *args, **kwargs):
    """
    load_tagged 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    参数：
    - graph：networkx 图对象。
    - source：路由、连接或测量数据的源端。

    """
    path = os.path.join(graph_directory, f'{source}_{tag}.graphml')
    print('loading from', path)
    return load_from_file(graph, path, *args, **kwargs)


def load_from_file(graph: nx.DiGraph, file_path, node_prefix='internet_'):
    """
    load_from_file 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    参数：
    - graph：networkx 图对象。

    """
    inet_graph: nx.Graph = load_graph(file_path)

    for src, dst, data in inet_graph.edges.data():
        graph.add_edge(node_prefix + src, node_prefix + dst, **data)


def fetch_to_graph(graph: nx.DiGraph, module, *args, **kwargs):
    """
    从外部数据源抓取数据并转换为当前模块使用的统一结构。

    参数：
    - graph：networkx 图对象。

    """
    add_to_graph(graph, module.fetch(), *args, **kwargs)


def add_to_graph(graph: nx.DiGraph, measurements: List[Measurement], node_prefix=''):
    """
    把一组延迟测量结果写入 networkx 图的边属性。

    参数：
    - graph：networkx 图对象。
    - measurements：统一延迟测量记录列表。

    """
    for m in measurements:
        if m.source == m.destination:
            continue

        src = f'{node_prefix}{m.source}'
        dst = f'{node_prefix}{m.destination}'

        graph.add_edge(src, dst, latency=m.avg)


def save_graph(g: nx.Graph, path: str) -> None:
    """
    把互联网延迟图保存为带日期戳的 graphml 文件，并刷新 latest 文件。

    参数：
    - path：最短路径结果，包含从源到目的的所有拓扑顶点。

    """
    nx.write_graphml(g, path=path)


def load_graph(path: str) -> nx.Graph:
    """
    load_graph 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    参数：
    - path：最短路径结果，包含从源到目的的所有拓扑顶点。

    """
    return nx.read_graphml(path)
