"""Ether 互联网延迟图生成命令，抓取 cloudping、gcloudping、wondernetwork 等数据源并保存为 graphml 文件。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【CLI 层】—— 数据抓取命令行入口。

用法:
    python -m ether.cli.inet

行为:
    用 ThreadPoolExecutor(4) 并发跑 3 个数据源 (cloudping / gcloudping / wondernetwork)
    每个数据源:
      1) 抓取过去 7 天数据 (fetch())
      2) 保存为 <source>_<YYYY_MM_DD>.graphml (日期戳版本,可重现)
      3) 覆盖 <source>_latest.graphml      (最新版本,默认使用)

    输出目录: ether/inet/graphs/

对 CSAC 论文的接口:
    - 论文可重现: 引用日期戳版本 ("用的是 2020_06_20 的数据")
    - 更新数据: 想用最新延迟时跑这个命令
    - 离线环境: ether 自带 6 个 graphml 文件,可直接用
================================================================================
"""

import os
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

import networkx as nx

from ether.inet.fetch import sources
from ether.inet.graph import add_to_graph, save_graph, graph_directory


def fetch_and_save(dirname, name, source):
    """
    抓取一个数据源的数据,保存为日期戳版本 + latest 版本两份 graphml。

    参数:
    - dirname: graphml 输出目录 (ether/inet/graphs/)
    - name:    数据源名 ('cloudping' / 'gcloudping' / 'wondernetwork')
    - source:  对应数据源模块 (有 fetch() 方法)
    """
    today = datetime.now().strftime("%Y_%m_%d")
    graph = nx.DiGraph()
    print('fetching from', name)
    add_to_graph(graph, source.fetch())

    filename = os.path.join(dirname, f'{name}_{today}.graphml')
    save_graph(graph, filename)
    print('saved', filename)

    filename = os.path.join(dirname, f'{name}_latest.graphml')
    save_graph(graph, filename)
    print('saved', filename)


def main():
    """
    CLI 入口: ThreadPoolExecutor(4) 并发跑 3 个数据源,阻塞等所有完成。
    """
    with ThreadPoolExecutor(4) as pool:
        futures = list()

        for name, source in sources.items():
            ftr = pool.submit(fetch_and_save, graph_directory, name, source)
            futures.append(ftr)

        for ftr in futures:
            ftr.result()


if __name__ == '__main__':
    main()
