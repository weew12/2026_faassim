# topologies：faas-sim / Ether 拓扑构建样例

本样例用于演示 faas-sim / Ether 中常见拓扑构建方式，重点展示节点、链路、连接、路由和官方场景拓扑的基本使用方法。

## 运行方式

将 `topologies/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/topologies/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何使用 `Node`、`Link` 和 `Connection` 构造最小拓扑；
2. 如何构造边缘-云星型拓扑；
3. 如何构造共享瓶颈链路拓扑；
4. 如何使用官方 `UrbanSensingScenario`；
5. 如何查询节点之间的 `Route`；
6. 如何导出拓扑节点、边、路由和摘要信息。

## 内置拓扑

样例包含四类拓扑：

```text
minimal            最小二节点拓扑
edge_cloud_star    多边缘节点到云端的星型拓扑
bottleneck         共享瓶颈链路拓扑
urban_sensing      官方 UrbanSensingScenario 拓扑
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/topologies/outputs/
```

主要包括：

```text
topology_nodes.csv
topology_edges.csv
topology_routes.csv
topology_summary.csv
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
