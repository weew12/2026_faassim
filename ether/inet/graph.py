"""互联网延迟图处理文件，负责 graphml 文件路径管理、图保存、图加载以及把测量数据写入拓扑边。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【数据层】—— 真实云区域延迟图加载/保存。

    graph_directory = ether/inet/graphs/  ← 6 个 graphml 数据文件
    3 个数据源: cloudping (AWS) / gcloudping (GCP) / wondernetwork

    主要函数:
      load_latest(graph, source)         ← 加载 <source>_latest.graphml
      load_tagged(graph, source, tag)    ← 加载 <source>_<tag>.graphml
      load_from_file(graph, path)        ← 读 graphml,加 internet_ 前缀,写入图
      fetch_to_graph(graph, module)      ← 在线抓数据
      add_to_graph(graph, measurements)  ← 把 measurements 写进图
      save_graph(g, path)                ← nx.write_graphml
      load_graph(path)                   ← nx.read_graphml

设计哲学:
    1. 节点前缀 'internet_': 避免和 topology 内部顶点冲突
       (配合 topology.py _update_rtt 的 elif 'latency' 分支)
    2. 双源支持: graphml 数据 (含 latency 字段) + 在线抓取 (Measurement)
    3. 数据可重现: 6 个 graphml 文件带日期戳 (2020_05_18 / 2020_06_20 / latest)

对 CSAC 论文的接口:
    - Topology.load_inet_graph('cloudping') 加载真实云区域延迟
    - 多区域调度实验 (跨大洲 RTT)
    - 数据可重现 (commit 固定的 graphml)
================================================================================
"""

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
    加载指定数据源 + tag 版本的 graphml 到 graph 中。

    参数：
    - graph：networkx 图对象。
    - source：路由、连接或测量数据的源端。
    - tag: 版本标签, 如 'latest' / '2020_05_18'
    """
    path = os.path.join(graph_directory, f'{source}_{tag}.graphml')
    print('loading from', path)
    return load_from_file(graph, path, *args, **kwargs)


def load_from_file(graph: nx.DiGraph, file_path, node_prefix='internet_'):
    """
    读 graphml 文件,把每个节点加 node_prefix 前缀后,边属性原样写入 graph。

    参数：
    - graph：networkx 图对象。
    - file_path: graphml 文件路径
    - node_prefix: 节点名前缀,默认 'internet_' (避免和拓扑内部顶点冲突)

    ─────────────────────────────────────────────────────────────
    【设计意图】为什么加 'internet_' 前缀?
    ─────────────────────────────────────────────────────────────
    避免命名空间冲突:
        - 用户节点: cloudvm_0, rpi3_0, switch_lan_0
        - internet 节点: 不加前缀会撞名 (如 'us-east-1' 可能被误用)
    加 'internet_' 前缀后:
        - 'us-east-1' → 'internet_us-east-1'  (图顶点唯一)
    同时配合 topology.py 的 _update_rtt 双源处理:
        - ether 自己的边 → 'connection' 字段 (Connection 对象)
        - internet 边   → 'latency' 字段 (数值)
    ─────────────────────────────────────────────────────────────
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
    读 graphml 文件,返回 networkx 图对象(封装 nx.read_graphml)。

    参数：
    - path：graphml 文件路径
    """
    return nx.read_graphml(path)
