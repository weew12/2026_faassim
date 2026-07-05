# topologies：faas-sim / Ether 拓扑构建样例

本样例用于演示 faas-sim / Ether 中常见拓扑构建方式，重点展示节点、链路、连接、路由和官方场景拓扑的基本使用方法。

## 运行方式

将 `topologies/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/topologies/main.py
```

## 文件结构

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

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 不同规模边缘拓扑生成；
2. 云边多层拓扑；
3. 多城市/多区域拓扑；
4. 带异构节点标签的拓扑；
5. 面向缓存调度实验的节点分区与边缘集群建模。
