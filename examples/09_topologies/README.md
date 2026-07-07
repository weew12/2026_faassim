# 09_topologies：faas-sim / Ether 拓扑构建样例

本样例用于演示 faas-sim / Ether 中常见拓扑构建方式，重点展示节点、链路、连接、路由和官方场景拓扑的基本使用方法。

## 运行方式

将 `topologies/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/09_topologies/main.py
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

> faas-sim 的 `Topology` 类本身就是 `networkx.DiGraph` 子类，拥有 `.nodes() / .edges() / .add_edge()` 等方法，
> 本样例通过 `inspectors.get_graph()` 直接把 `topology` 当图遍历使用（不需要从子字段查找）。

## 输出文件

运行结束后，结果会保存到：

```text
examples/09_topologies/outputs/
```

实际生成：

```text
topology_nodes.csv     # 每个拓扑图中的节点（Node / Link / Switch）
topology_edges.csv     # 每个拓扑图中的有向边（directed / latency / connection_source / connection_target）
topology_routes.csv    # 每个拓扑中代表性 source → sink 的 route（含 rtt_ms / hop_count / 瓶颈链路）
topology_summary.csv   # 4 个拓扑的摘要表
```

> `topology_edges.csv` 中一行 = 一条有向边。faas-sim 的 `add_connection(a, b)` 会插入两条有向边
> （a→b 和 b→a），所以一条物理连接占 2 行。

## 关键导出与图

### 1. `topology_summary.csv` —— 4 个拓扑规模一览

预期输出（ID 每次不同）：

```text
       topology  explicit_node_count  explicit_link_count  graph_node_count  graph_edge_count  route_records
        minimal                   2                    1                 3                 4              1
edge_cloud_star                   5                    6                13                24              4
     bottleneck                   3                    4                 9                16              2
  urban_sensing                   0                    0               117               224              4
```

`explicit_*` 是样例显式构造的节点 / 链路数；`graph_*` 是 `Topology` 图里实际存在的对象数
（每个 Node 和 Link 都会成为 graph 的一个节点；每个 Connection 会成为 2 条有向边）。

### 2. `topology_routes.csv` —— 路由与瓶颈链路

每条记录是一个 source → sink 的 `Route` 查询结果：

- `rtt_ms`             端到端往返时延
- `hop_count`          路径上的链路数
- `path`               完整路径（节点 + 链路）
- `hops`               路径上的链路名（用 `→` 连接）
- `bottleneck_link`    整条路径上 bandwidth 最小的链路
- `bottleneck_bandwidth_mbps`  瓶颈链路带宽

举例 `bottleneck` 拓扑 `edge_a → cloud_node`：

```text
hops: edge_a_access → bottleneck → cloud_access
bottleneck_link: bottleneck
bottleneck_bandwidth_mbps: 10
```

`urban_sensing` 中 `server_0 → tx2_9` 路径：

```text
path: server_0 → link_server_0 → switch_lan_11 → switch_cloudlet_0 →
      up_cloudlet_0 → internet → down_shared_1 → shared_1 →
      switch_lan_6 → link_tx2_9 → tx2_9
hops: link_server_0 → up_cloudlet_0 → down_shared_1 → shared_1 → link_tx2_9
bottleneck_link: down_shared_1
```

> 这条路径解释了 05_image_pull_network 样例为什么 server_0 的瓶颈是 cloudlet 上联：
> `server_0` 在 cloudlet 里，需要走 `up_cloudlet_0 (1 Gbps) → internet → down_shared_1` 才能到达其他节点。

### 3. 论文 demo 关键图 —— 拓扑规模对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/09_topologies/outputs/topology_summary.csv")
fig, ax = plt.subplots(figsize=(9, 4))
x = range(len(df))
width = 0.35
ax.bar([i - width/2 for i in x], df["graph_node_count"], width, label="graph_node_count", color="steelblue")
ax.bar([i + width/2 for i in x], df["graph_edge_count"], width, label="graph_edge_count", color="darkorange")
ax.set_xticks(list(x))
ax.set_xticklabels(df["topology"], rotation=15, ha="right")
ax.set_ylabel("count")
ax.set_title("Topology size: graph nodes vs edges")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，5 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| 所有 4 个 topology 的 `graph_node_count > 0` | `summary.graph_node_count.min() > 0` |
| 所有 4 个 topology 的 `graph_edge_count > 0` | `summary.graph_edge_count.min() > 0` |
| `topology_edges.csv` 行数 == `summary.graph_edge_count` 之和 | `len(edges) == summary.graph_edge_count.sum()` |
| `topology_routes.csv` 行数 == `summary.route_records` 之和 | `len(routes) == summary.route_records.sum()` |
| `urban_sensing` 现在能查到路由 | `routes[routes.topology=="urban_sensing"].shape[0] >= 1` |

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

该文件负责兼容式读取拓扑底层图结构（`Topology` 本身），并提取节点、边、路由和摘要信息。

关键设计：

- `get_graph(topology)` 直接返回 `topology` 本身（faas-sim 的 `Topology` 继承自 `networkx.DiGraph`）。
- `collect_route_records` 对 urban_sensing 这类没有 case.nodes 的复杂拓扑，
  从 graph 中按前缀去重选 representative sources，sink 优先选 `cloudlet / cloud` 节点。

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