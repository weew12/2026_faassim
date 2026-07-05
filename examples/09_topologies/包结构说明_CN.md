# topologies 包结构说明

`topologies` 是 faas-sim / Ether 拓扑构建样例包，用于演示如何构造、检查和导出网络拓扑信息。

## 目录结构

```text
topologies/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── inspectors.py
├── main.py
├── README_CN.md
└── topology_builders.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 构造多个拓扑样例；
2. 打印拓扑基本信息；
3. 调用分析模块导出拓扑结果；
4. 输出拓扑摘要。

### `topology_builders.py`

拓扑构造文件。

该文件提供：

```text
build_minimal_topology()
build_edge_cloud_star_topology()
build_bottleneck_topology()
build_urban_sensing_topology()
build_all_topology_cases()
```

用于演示从最小拓扑到官方场景拓扑的不同构建方式。

### `inspectors.py`

拓扑检查工具文件。

该文件负责兼容式读取拓扑底层图结构，并提取节点、边、路由和摘要信息。

### `analysis.py`

结果导出文件。

该文件负责导出：

```text
topology_nodes.csv
topology_edges.csv
topology_routes.csv
topology_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/topologies/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中对拓扑构建方式说明不足的问题，为后续网络流、镜像拉取、数据本地性和边缘调度实验提供基础。
