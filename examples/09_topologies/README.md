# 09_topologies：faas-sim / Ether 拓扑构建样例

本样例演示 faas-sim / Ether 中常见拓扑构建方式，重点展示**节点、链路、连接、路由和官方场景拓扑**的基本使用方法。

## 运行方式

在项目根目录运行：

```bash
python -u examples/09_topologies/main.py
python -u examples/09_topologies/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 png+pdf 到 `figures/`。
样例在 `topology_builders.py` 中固定 `RANDOM_SEED = 20260707`，避免 `UrbanSensingScenario` 的随机采样导致输出文件和 README 数值漂移。

## 样例目标

该样例主要回答以下问题：

1. 如何使用 `Node`、`Link` 和 `Connection` 构造最小拓扑；
2. 如何构造边缘-云星型拓扑；
3. 如何构造共享瓶颈链路拓扑；
4. 如何使用官方 `UrbanSensingScenario`；
5. 如何查询节点之间的 `Route`；
6. 如何导出拓扑节点、边、路由和摘要信息。

## 内置拓扑

样例包含 4 类拓扑：

| 拓扑 | explicit_node | explicit_link | graph_node | graph_edge | route |
|---|---|---|---|---|---|
| minimal | 2 | 1 | 3 | 4 | 1 |
| edge_cloud_star | 5 | 6 | 13 | 24 | 4 |
| bottleneck | 3 | 4 | 9 | 16 | 2 |
| urban_sensing | 0 | 0 | **117** | **224** | 4 |

> faas-sim 的 `Topology` 类本身就是 `networkx.DiGraph` 子类，拥有 `.nodes() / .edges() / .add_edge()` 等方法，
> 本样例通过 `inspectors.get_graph()` 直接把 `topology` 当图遍历使用（不需要从子字段查找）。

## 输出文件

运行结束后，结果会保存到 `outputs/`：

```text
topology_nodes.csv                  # 每个拓扑图中的节点（Node / Link / Switch）
topology_edges.csv                  # 每个拓扑图中的有向边（directed / latency / connection_source / connection_target）
topology_routes.csv                 # 每个拓扑中代表性 source → sink 的 route（含 rtt_ms / hop_count / 瓶颈链路）
topology_summary.csv                # 4 个拓扑的摘要表
topology_paper_highlight.csv        # 论文 demo 关键摘要（14 条 metric/value）
topology_self_check.csv             # 数据自检（10 项 PASS/FAIL）
```

绘图脚本生成 4 张图到 `figures/`：

```text
fig01_topology_size_comparison.png/pdf       # 4 个拓扑的节点数 / 边数 / 路由数对比柱状图
fig02_per_topology_node_distribution.png/pdf # 每个拓扑的节点类型堆叠柱状图
fig03_route_overview.png/pdf                # 每个拓扑的 rtt_ms / hop_count / bottleneck_bandwidth scatter
fig04_paper_highlight_metrics.png/pdf       # 论文 demo 关键摘要指标条形图
```

## 论文 demo 关键摘要（14 条 paper highlight）

| metric | value | note |
|---|---|---|
| total_topologies | 4 | 构建的拓扑样例总数（minimal/edge_cloud_star/bottleneck/urban_sensing） |
| total_graph_nodes | 142 | 4 个拓扑的图节点总数 |
| total_graph_edges | 268 | 4 个拓扑的图边总数（有向边） |
| total_route_records | 11 | 4 个拓扑的 route 总数 |
| minimal_graph_nodes | 3 | minimal 拓扑的图节点数 |
| urban_sensing_graph_nodes | 117 | urban_sensing 拓扑的图节点数（最大） |
| urban_sensing_graph_edges | 224 | urban_sensing 拓扑的图边数 |
| **size_scaling_minimal_to_urban** | **39** | **urban_sensing 节点数 / minimal 节点数（论文 demo 关键比值）** |
| avg_route_rtt_ms | 68.5154 | 所有成功路由的平均 RTT（ms） |
| max_route_rtt_ms | 96.1468 | 所有成功路由的最大 RTT（ms） |
| avg_route_hop_count | 3.5455 | 所有成功路由的平均 hop 数 |
| max_route_hop_count | 6 | 所有成功路由的最大 hop 数 |
| route_success_count | 11 | 成功的 route 数（route_available == True） |
| route_failure_count | 0 | 失败的 route 数 |

## 10 项数据自检（10 / 10 PASS）

| check_id | 含义 |
|---|---|
| 01_total_topologies_is_4 | 4 个拓扑都构建成功 |
| 02_all_nodes_positive | 所有拓扑的 graph_node_count > 0 |
| 03_all_edges_positive | 所有拓扑的 graph_edge_count > 0 |
| 04_edges_total_matches_summary | topology_edges 总行数 == summary.graph_edge_count 之和 |
| 05_routes_total_matches_summary | topology_routes 总行数 == summary.route_records 之和 |
| 06_urban_sensing_has_routes | urban_sensing 能查到路由（>= 1） |
| 07_all_topology_has_routes | 所有 topology 至少有 1 个 route |
| 08_nodes_total_matches_summary | topology_nodes 总行数 == summary.graph_node_count 之和 |
| 09_routes_has_required_columns | topology_routes 列名包含 topology/source/sink |
| 10_paper_self_consistent | paper_highlight 数字与 summary 一致 |

## 文件说明

### `main.py`

样例主入口。职责包括：

1. 构造 4 个拓扑样例；
2. 打印拓扑基本信息；
3. 调用分析模块导出拓扑结果；
4. 打印论文 demo 关键摘要 + 数据自检。

### `topology_builders.py`

拓扑构造文件。提供：

- `build_minimal_topology()`：最小二节点拓扑
- `build_edge_cloud_star_topology(edge_count=4)`：边缘-云星型拓扑
- `build_bottleneck_topology()`：共享瓶颈链路拓扑
- `build_urban_sensing_topology()`：官方 UrbanSensingScenario
- `build_all_topology_cases()`：构造所有拓扑样例，并固定随机种子以保证 `UrbanSensingScenario` 可复现

### `inspectors.py`

拓扑检查工具文件。负责：

- `get_graph(topology)`：直接返回 topology 本身（faas-sim 的 Topology 继承自 networkx.DiGraph）
- `collect_graph_nodes`：收集节点信息（Node / Link / Switch）
- `collect_graph_edges`：收集边信息（含 latency / connection metadata）
- `collect_route_records`：收集代表性 source → sink 的 route
- `build_topology_summary`：生成单个拓扑的摘要记录

### `analysis.py`

指标导出与分析文件。负责：

- 导出 `topology_nodes` / `topology_edges` / `topology_routes` / `topology_summary`
- 生成 `topology_paper_highlight`（14 条论文 demo 关键摘要）
- 生成 `topology_self_check`（10 项数据自检）

### `plot.py`

绘图脚本。读 `outputs/` CSV，输出 `figures/` 下 4 张 png+pdf：

1. **fig01_topology_size_comparison** —— 4 个拓扑的节点数 / 边数 / 路由数对比（论文 demo 关键图）
2. **fig02_per_topology_node_distribution** —— 节点类型堆叠柱状图
3. **fig03_route_overview** —— 每个拓扑的 rtt_ms / hop_count / bottleneck_bandwidth scatter（三子图）
4. **fig04_paper_highlight_metrics** —— 论文 demo 关键摘要条形图

### `outputs/`

CSV 输出目录。

### `figures/`

绘图输出目录（运行 plot.py 后生成）。

## 论文叙事点

> **"faas-sim 的 Topology 类继承 networkx.DiGraph，因此 4 种代表性拓扑（minimal/edge_cloud_star/bottleneck/urban_sensing）可直接作为有向图遍历，提取节点、边、路由和瓶颈链路。规模差异显著：minimal 仅 3 节点 4 边 1 路由；urban_sensing 在固定 seed 下达到 117 节点 224 边 4 路由；urban_sensing / minimal 节点数比值达 39×。4 个拓扑共 11 条成功路由，RTT 范围 14-96ms，平均 hop 数 3.5455。"**

## 09 vs 02-08 demo 价值对比

| 维度 | 02_load_balancer | 03_skippy_scheduler | 04_network_flow | 05_image_pull_network | 06_resource_monitor | 07_trace_oracle | 08_degradation | 09_topologies |
|---|---|---|---|---|---|---|---|---|
| 仿真引擎 | faas-sim | faas-sim | Ether | faas-sim + docker | faas-sim + ResourceMonitor | faas-sim + Trace Oracle | faas-sim + Degradation Model | **faas-sim Topology 静态分析** |
| 拓扑 | 4-server 最小 | 4-server 最小 | 边缘→云端瓶颈 | 4-server + 1Gbps | 4-server 最小 | 4-server 最小 | 4-server 最小 | **4 种代表性拓扑对比** |
| 关注对象 | FunctionReplica 路由 | Pod 调度 | 网络 Flow | 镜像拉取 + 缓存 | CPU/内存利用率 | trace-driven 执行时间 | 节点竞争退化 | **拓扑规模 + 路由特征** |
| 是否跑仿真 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✗（静态分析）** |
| 探针 | invoke_dispatch_probe | schedule_probe + invoke_dispatch_probe | （不适用） | image_pull_probe + invoke_dispatch_probe | function_utilization + invoke_dispatch_probe | trace_oracle_sample + invoke_dispatch_probe | degradation_probe + invoke_dispatch_probe | （不适用） |
| 关键 metric | route_events | feasible_nodes_full | scaling_factor | cache_savings_seconds | overall_max_cpu_util | duration_match_ratio | max_active_requests_before | total_graph_nodes / size_scaling_minimal_to_urban |
| 论文 highlight | 11 条 | 10 条 | 11 条 | 12 条 | 15 条 | 9 条 | 13 条 | 14 条 |
| self-check | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 |
