"""Ether 互联网延迟图生成命令，抓取 cloudping、gcloudping、wondernetwork 等数据源并保存为 graphml 文件。"""

import os
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

import networkx as nx

from ether.inet.fetch import sources
from ether.inet.graph import add_to_graph, save_graph, graph_directory


def fetch_and_save(dirname, name, source):
    """
    从外部数据源抓取数据并转换为当前模块使用的统一结构。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。
    - source：路由、连接或测量数据的源端。

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
    main 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

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
