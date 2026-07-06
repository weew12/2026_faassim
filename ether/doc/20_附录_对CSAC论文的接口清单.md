# 20 · 附录 对论文的接口清单

> 本文档是跨文档的**索引/检索表**,按"实验需要什么 → ether 给什么"组织。看完这个,就知道 CSAC 论文实验要用 ether 的哪些接口。
>
> **建议用法**:做实验时直接查这个表 → 跳到对应子文档看细节

## 1. 资源建模

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 节点 CPU 容量 | `Node.capacity.cpu_millis`(毫核) | `core.py` |
| 节点内存容量 | `Node.capacity.memory`(字节) | `core.py` |
| 节点架构(x86/arm) | `Node.arch: str` | `core.py` |
| 节点类型/能力标签 | `Node.labels: Dict[str, str]` | `core.py` |
| 设备型号 | `labels['ether.edgerun.io/model']` | `blocks/nodes.py` |
| 设备能力(GPU/TPU) | `labels['ether.edgerun.io/capabilities/*']` | `blocks/nodes.py` |
| Capacity 工厂 | `Capacity(cpu_millis, memory)` | `core.py` |
| 预置设备工厂 | `nodes.rpi3` / `nodes.tx2` / `nodes.nx` / `nodes.coral` 等 | `blocks/nodes.py` |
| 内存字符串解析 | `util.parse_size_string("1Gi")` | `util.py` |

**对应文档**:

- [02_core](./02_core_核心类型与仿真引擎.md) § 4-6
- [10_blocks](./10_blocks_预置构造块.md) § 2
- [06_util_export_vis](./06_util_export_vis_工具与导出.md) § 2

## 2. 拓扑构建

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 单主机单元 | `Host(node, link_bw=1000)` | `cell.py` |
| 局域网单元(共享交换机) | `LANCell(nodes, backhaul=...)` | `cell.py` |
| 共享带宽链路 | `SharedLinkCell(nodes, shared_bandwidth=300)` | `cell.py` |
| 城市级重复部署 | `GeoCell(size, density, nodes)` | `cell.py` |
| 上下行非对称 | `UpDownLink(bw_down, bw_up, backhaul, latency_dist)` | `cell.py` |
| 移动 4G/5G 上联 | `MobileConnection(backhaul='internet')` | `blocks/cells.py` |
| 企业 ISP 上联 | `BusinessIsp(backhaul='internet')` | `blocks/cells.py` |
| 光纤到机房 | `FiberToExchange(backhaul='internet')` | `blocks/cells.py` |
| IoT 现场计算 | `IoTComputeBox(nodes, backhaul)` | `blocks/cells.py` |
| 边缘 Cloudlet | `Cloudlet(server_per_rack, racks, backhaul)` | `blocks/cells.py` |
| 用户节点 | `Client('user_name')` | `cell.py` |
| MQTT 代理 | `Broker('broker_name')` | `cell.py` |
| 物化到拓扑 | `topology.add(cell)` 或 `cell.generate()` | `topology.py` / `cell.py` |

**对应文档**:

- [03_cell](./03_cell_组合式拓扑单元DSL.md) § 4-8
- [10_blocks](./10_blocks_预置构造块.md) § 4

## 3. 链路时延

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 局域网时延分布 | `latency.lan` (~0.5ms 众数) | `qos/latency.py` |
| WiFi 时延分布 | `latency.wlan` (~3.5ms 众数) | `qos/latency.py` |
| 企业 ISP 时延分布 | `latency.business_isp` (~3.4ms 众数) | `qos/latency.py` |
| 移动运营商时延分布 | `latency.mobile_isp` (~21ms 众数) | `qos/latency.py` |
| 自定义时延分布 | `ParameterizedDistribution.lognorm((σ, scale, loc))` | `srds` |
| 单次采样时延 | `Connection.get_latency()` | `core.py` |
| 众数时延(稳定) | `Connection.get_mode_latency()` | `core.py` |
| 平均时延 | `Connection.get_mean_latency()` | `core.py` |

**对应文档**:

- [12_qos](./12_qos_链路时延分布.md) § 3-5
- [02_core](./02_core_核心类型与仿真引擎.md) § 3

## 4. 路由与 RTT

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 最短路径 | `Topology.path(src, dst)` | `topology.py` |
| 端到端路由 | `Topology.route(src, dst, use_mode=False)` | `topology.py` |
| 路由(稳定众数) | `Topology.route(src, dst, use_mode=True)` | `topology.py` |
| 单向时延(精确) | `Topology.latency(src, dst)` | `topology.py` |
| 单向时延(轻量 Vivaldi) | `Topology.latency(src, dst, use_coordinates=True)` | `topology.py` |
| 端到端 RTT | `route.rtt`(双向) | `core.py` |
| 路由路径 | `route.path`(完整顶点序列) | `core.py` |
| 实际承载带宽的 Link | `route.hops`(过滤透明链路) | `core.py` |
| 路由缓存 | `topology._route_cache[(src, dst)]` | `topology.py` |
| 强制拓扑约束 | `add_connection` 拒绝 `Node→Node` 直连 | `topology.py` |
| 加载云区域延迟 | `Topology.load_inet_graph('cloudping')` | `topology.py` |

**对应文档**:

- [04_topology](./04_topology_DiGraph与路由缓存.md) § 3-5
- [13_inet](./13_inet_云区域延迟图.md) § 5

## 5. 流量与带宽仿真

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 创建网络流 | `Flow(env, size, route)` | `core.py` |
| 启动流(返回 SimPy Process) | `flow.start()` | `core.py` |
| 流端到端瓶颈带宽 | `flow.get_goodput_bps()`(取 min of hops) | `core.py` |
| 链路单流带宽分配 | `link.get_goodput_bps(flow)`(Mbit/s × 125000 × 0.97) | `core.py` |
| 链路公平份额 | `link.max_allocatable` | `core.py` |
| 链路当前流分配 | `link.allocation: Dict[Flow, float]` | `core.py` |
| 公平共享带宽算法 | `rebalance(triggering_flow, affected, links)` | `core.py` |
| 流加入触发重分 | `add_and_rebalance(flow)` | `core.py` |
| 流结束触发重分 | `remove_and_rebalance(flow)` | `core.py` |
| 非抢占背景流量 | `UninterruptingFlow(env, size, route)` | `core.py` |
| 受影响流 BFS 查找 | `collect_subnet(flow)` | `core.py` |
| 流传输主协程 | `flow.run()`(SimPy 协程) | `core.py` |
| 流已传字节 | `flow.sent`(中断时记录进度) | `core.py` |
| TCP 握手近似 | `1.5 × RTT / 1000` 秒 | `core.py` |
| Flow 协程中断重算 | `flow.process.interrupt(bw)`(rebalance 用) | `core.py` |

**对应文档**:

- [02_core](./02_core_核心类型与仿真引擎.md) § 8-12

## 6. 网络坐标(Vivaldi 轻量 RTT)

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| 创建 Vivaldi 坐标 | `VivaldiCoordinate()` | `vivaldi.py` |
| 单次更新坐标 | `execute(node, other, rtt)` | `vivaldi.py` |
| 估算节点距离 | `coord.distance_to(other)` | `vivaldi.py` |
| 调整位置 | `coord.apply_force(force, other)` | `vivaldi.py` |
| 通过 `Topology` 用 Vivaldi | `latency(src, dst, use_coordinates=True)` | `topology.py` |
| 收敛性可证明 | Vivaldi 算法有论文(SIGCOMM 2004) | 引用 [1] |

**对应文档**:

- [05_vivaldi](./05_vivaldi_网络坐标.md) § 4-6

## 7. 真实云区域延迟数据

| 论文实验要素 | ether 接口 | 所在文件 |
|---|---|---|
| AWS 区域延迟 | `Topology.load_inet_graph('cloudping')` | `topology.py` / `inet/graph.py` |
| GCP 区域延迟 | `Topology.load_inet_graph('gcloudping')` | `topology.py` / `inet/graph.py` |
| WonderNetwork 数据 | `Topology.load_inet_graph('wondernetwork')` | `topology.py` / `inet/graph.py` |
| 抓取最新数据 | `python -m ether.cli.inet` | `cli/inet.py` |
| 自定义测量数据 | `add_to_graph(graph, my_measurements)` | `inet/graph.py` |
| 数据文件位置 | `ether/inet/graphs/*_latest.graphml` | 数据文件 |

**对应文档**:

- [13_inet](./13_inet_云区域延迟图.md) § 5-6
- [14_cli](./14_cli_命令行工具.md) § 3

## 8. 预置场景(直接用)

| 论文场景 | ether 场景 | 所在文件 |
|---|---|---|
| 多云区域调度 | `CloudRegionsScenario(regions, region_size)` | `scenarios/cloudregions.py` |
| 工业 IoT(工厂边缘) | `IndustrialIoTScenario(num_premises)` | `scenarios/industrialiot.py` |
| 城市感知(Array of Things) | `UrbanSensingScenario(num_cells)` | `scenarios/urbansensing.py` |

**对应文档**:

- [11_scenarios](./11_scenarios_预置场景.md) 全文

## 9. 可视化与导出

| 论文需求 | ether 接口 | 所在文件 |
|---|---|---|
| NetworkX 静态图(主图) | `vis.draw_basic(topology)` | `vis.py` |
| PyVis 交互 HTML(补充材料) | `converter.pyvis.topology_to_pyvis(t).show()` | `converter/pyvis.py` |
| 拓扑导出 JSON(TAM 格式) | `export.export_to_tam_json(t, file, value_projector)` | `export.py` |
| 节点按数值着色(外部工具) | `value_projector: Callable[[Node], int]` | `export.py` |

**对应文档**:

- [06_util_export_vis](./06_util_export_vis_工具与导出.md) § 3-4
- [15_converter](./15_converter_外部格式转换.md) § 5-7

## 10. 调试与扩展

| 论文需求 | ether 接口 | 所在文件 |
|---|---|---|
| 节点名字唯一生成 | `counters[type].__next__()` | `cell.py` / `blocks/*.py` |
| Configurator 模式 | `as_host(node, *configurators)` | `blocks/hosts.py` |
| 自定义 UpDownLink | 继承 `UpDownLink` | `cell.py` / `blocks/cells.py` |
| 自定义 Cell | 继承 `Cell`,重写 `materialize` | `cell.py` |
| 自定义场景 | 继承 `Scenario` 类,有 `materialize` 方法 | `scenarios/*` |
| 扩展 rebalance 行为 | 修改 `rebalance` 函数(注意 SimPy 兼容) | `core.py` |
| TCP 多流退化 | 修改 `Link.get_goodput_bps`(注释里给的扩展点) | `core.py` |

**对应文档**:

- [02_core](./02_core_核心类型与仿真引擎.md) § 9(`get_goodput_bps` 注释)
- [03_cell](./03_cell_组合式拓扑单元DSL.md) § 3
- [10_blocks](./10_blocks_预置构造块.md) § 3(Configurator 模式)

## 11. 完整调用流程示例

### 11.1 CSAC 调度决策时怎么用 ether

```python
# 1. 选场景 + 物化
from ether.topology import Topology
from ether.scenarios.industrialiot import IndustrialIoTScenario

t = Topology()
t.add(IndustrialIoTScenario(num_premises=3))
t.load_inet_graph('cloudping')

# 2. CSAC 决定:把函数 f 部署到哪个节点
# CSAC 需要估算"部署到节点 X 的网络成本"
# 用 ether 的 latency() 算 RTT,用 Flow 算实际传输耗时

# 2.1 算 RTT(双向)
rtt = t.route(node_a, node_b).rtt   # 精确模式
rtt_mode = t.route(node_a, node_b, use_mode=True).rtt   # 稳定众数
one_way = t.latency(node_a, node_b)  # 单向 = RTT / 2

# 2.2 算实际传输耗时(考虑带宽争抢)
from ether.core import Flow, Route

route = t.route(node_a, node_b)
flow = Flow(env=env, size=image_size_bytes, route=route)
flow.start()                                # 启动 SimPy 协程
# 等待 flow.process 完成
# 实际耗时 = env.now - flow_start_time

# 2.3 轻量估算(用 Vivaldi)
quick_rtt = t.latency(node_a, node_b, use_coordinates=True)
```

### 11.2 实验场景搭建

```python
# 1. 自定义异构边缘场景
from ether.cell import LANCell, SharedLinkCell, UpDownLink
from ether.blocks import nodes
from ether.blocks.cells import MobileConnection, Cloudlet
from ether.qos import latency

# 1.1 多个共享链路的小区(异构节点)
neighborhood = lambda size: SharedLinkCell(
    nodes=[
        IoTComputeBox([nodes.nuc] + [nodes.tx2] * size),  # 异构
        [nodes.rpi3] * (size * 2)                          # 传感器
    ],
    shared_bandwidth=500,
    backhaul=MobileConnection('internet')
)

# 1.2 城市级重复(非固定规模)
from ether.cell import GeoCell
from srds import ParameterizedDistribution

city = GeoCell(
    size=5,                                          # 5 个城区
    density=ParameterizedDistribution.lognorm((0.82, 2.02)),  # 节点数从分布采样
    nodes=[neighborhood]
)

# 1.3 Cloudlet
city_cloudlet = Cloudlet(server_per_rack=10, racks=3, backhaul=FiberToExchange('internet'))

# 2. 物化
t = Topology()
t.add(city)
t.add(city_cloudlet)
t.load_inet_graph('cloudping')

# 3. 可视化
import matplotlib.pyplot as plt
from ether.vis import draw_basic
fig, ax = plt.subplots(figsize=(12, 8))
draw_basic(t)
plt.savefig('my_topology.pdf', bbox_inches='tight', dpi=300)
```

### 11.3 数据导出供外部分析

```python
import json

# 按节点 CPU 利用率导出
def cpu_value(node):
    return node.capacity.cpu_millis if hasattr(node, 'capacity') else 0

export.export_to_tam_json(t, 'topology.json', cpu_value)
# 然后用 d3.js / Gephi / Cytoscape 打开
```

## 12. 实验设计 checklist(对 CSAC 论文)

### 12.1 必须做

- [ ] 选定一个或多个 `scenarios` 模板
- [ ] 决定节点异构性(用 `blocks/nodes.py` 哪种设备)
- [ ] 决定回传类型(`MobileConnection` / `BusinessIsp` / `FiberToExchange`)
- [ ] 决定时延分布(`qos/latency.py` 4 个之一)
- [ ] 加载云区域延迟(`load_inet_graph('cloudping')`)

### 12.2 推荐做

- [ ] 多个网络条件对比(改 `qos` 分布)
- [ ] 多个场景规模(`num_cells` / `num_premises`)
- [ ] 公平共享 vs 非抢占(`Flow` vs `UninterruptingFlow`)
- [ ] 拓扑 RTT vs 坐标 RTT(`latency(use_coordinates=...)`)

### 12.3 可选做(提升论文质量)

- [ ] 交互式补充材料(PyVis HTML)
- [ ] 高 dpi 主图(matplotlib)
- [ ] 自定义时延分布(5G vs 4G)
- [ ] 自定义 rebalance 行为(模拟 TCP 多流退化)

## 13. 不在 ether 范围内的功能

ether 是**网络仿真子包**,以下功能不在其范围内:

| 不在范围 | 用什么代替 |
|---|---|
| FaaS 调度算法 | faas-sim/sim/faas/* |
| 容器镜像管理 | faas-sim/sim/docker.py |
| 工作负载生成 | faas-sim/sim/workload/* |
| 镜像拉取编排 | faas-sim/sim/net.py + ether.Flow |
| 调度器选节点 | faas-sim/sim/faas/* + ether.Topology 查询 |

ether 只负责**网络本身**的建模与仿真,不负责调度决策本身。

**文档生成时间**:2026-07-06
**对应代码版本**:ether commit `7aaf515a3d549f43d6d92599669afe18845f84e3`
