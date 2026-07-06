# 14 · cli 命令行工具

> 本文档解析 `ether/cli/` 子包(2 个文件,共 53 行),提供命令行入口,用于抓取最新云区域延迟并保存为 graphml。
>
> **核心内容**:`cli/inet.py` —— 并发抓取 3 个数据源,保存为 graphml

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 2 | 包入口(空 docstring) |
| `inet.py` | 53 | 抓取并保存 graphml 数据 |

## 2. `cli/inet.py` 完整解析

### 完整代码

```python
"""Ether 互联网延迟图生成命令,抓取 cloudping、gcloudping、wondernetwork 等数据源并保存为 graphml 文件。"""

import os
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

import networkx as nx

from ether.inet.fetch import sources
from ether.inet.graph import add_to_graph, save_graph, graph_directory


def fetch_and_save(dirname, name, source):
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
    with ThreadPoolExecutor(4) as pool:
        futures = list()

        for name, source in sources.items():
            ftr = pool.submit(fetch_and_save, graph_directory, name, source)
            futures.append(ftr)

        for ftr in futures:
            ftr.result()


if __name__ == '__main__':
    main()
```

### `fetch_and_save(dirname, name, source)` 行为

| 步骤 | 行为 |
|---|---|
| 1. 命名 | `today = datetime.now().strftime("%Y_%m_%d")` 如 `"2026_07_06"` |
| 2. 新建图 | `graph = nx.DiGraph()` |
| 3. 抓取数据 | `add_to_graph(graph, source.fetch())` |
| 4. 保存日期戳版本 | `<name>_<today>.graphml` 如 `cloudping_2026_07_06.graphml` |
| 5. 保存 latest 版本 | `<name>_latest.graphml` |

**为什么保存两份**:

- **日期戳版本**:可重现实验(论文里"用的是哪天的数据"可以精确指出)
- **latest 版本**:始终指向最新数据(默认情况下 ether 用这个)

### `main()` 行为

```python
with ThreadPoolExecutor(4) as pool:        # 4 个工作线程
    futures = list()
    for name, source in sources.items():    # 3 个数据源:cloudping / gcloudping / wondernetwork
        ftr = pool.submit(fetch_and_save, graph_directory, name, source)
        futures.append(ftr)
    for ftr in futures:
        ftr.result()                         # 阻塞等所有完成
```

**并发抓取** 3 个数据源,各自一个线程 + 一个备用线程(4 个池 3 个任务)。

## 3. 用法

### 命令行运行

```bash
# 在 ether 包根目录
python -m ether.cli.inet
```

### 程序化调用

```python
from ether.cli.inet import fetch_and_save
from ether.inet.fetch import sources
from ether.inet.graph import graph_directory

for name, source in sources.items():
    fetch_and_save(graph_directory, name, source)
```

### 典型输出

```
fetching from cloudping
saved C:\path\to\ether\inet\graphs\cloudping_2026_07_06.graphml
saved C:\path\to\ether\inet\graphs\cloudping_latest.graphml
fetching from gcloudping
saved ...\gcloudping_2026_07_06.graphml
saved ...\gcloudping_latest.graphml
fetching from wondernetwork
saved ...\wondernetwork_2026_07_06.graphml
saved ...\wondernetwork_latest.graphml
```

## 4. 注意事项

### 网络要求

- 需要能访问公网(调用 `requests.get` 到 cloudping / GCP / wondernetwork 的 API)
- 如果离线环境,脚本会失败 → 用本地 `*.graphml` 文件

### 数据格式

- `cloudping` 和 `gcloudping` 走 `Measurement` 格式,`add_to_graph` 转边
- `wondernetwork` 走自己的抓取逻辑,统一转 `Measurement`

### 数据版本

- ether 仓库**自带的 graphml 是 2020 年的**
- 想用最新数据,运行 `python -m ether.cli.inet`
- 论文里"用的是哪天的数据" → 引用日期戳版本

## 5. 对论文的用处

| 论文场景 | 价值 |
|---|---|
| **论文可重现性** | 日期戳版本可精确指出"用的是哪天的 cloudping 数据" |
| **最新数据** | 想用最新云区域延迟时,跑这个 CLI |
| **自定义数据源** | 模仿 `cloudping.py` 写一个自己的 fetch,然后注册到 `sources` 字典 |

### 论文实验设置建议

```python
# 实验 1:用 2020 年 6 月数据(ether 自带,确保可重现)
# 不需要运行 CLI,直接用 ether/inet/graphs/cloudping_2020_06_20.graphml

# 实验 2:用最新数据
# 运行 python -m ether.cli.inet
# 然后 load_inet_graph('cloudping') 默认会读 _latest.graphml
```
