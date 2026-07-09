# Ether 组成与源码地图

## 1. 顶层目录

`ether` 目录大致可以分为 8 组：

```text
ether/
  core.py              核心类型与网络流仿真
  topology.py          拓扑图、路由、RTT
  cell.py              组合式拓扑单元 DSL
  blocks/              预置节点和网络单元
  scenarios/           预置完整场景
  inet/                云区域/互联网延迟图
  qos/                 链路时延分布
  converter/ vis.py    可视化与格式转换
  export.py            拓扑导出
  vivaldi.py           网络坐标
  util.py              容量字符串解析工具
```

## 2. core.py：核心类型与网络流

`core.py` 是 Ether 最底层、最重要的文件。

主要对象：

| 对象 | 含义 |
|---|---|
| `Capacity` | CPU/内存资源容量 |
| `Node` | 计算节点、存储节点、云节点、边缘节点 |
| `Connection` | 拓扑边，保存连通关系和时延 |
| `Link` | 链路带宽资源 |
| `Route` | 源到目标的一条路径 |
| `Flow` | 一次网络数据传输 |
| `add_and_rebalance()` | 新流加入后重分配带宽 |
| `remove_and_rebalance()` | 流结束后释放带宽并重分配 |
| `rebalance()` | 对受影响流执行带宽重算和中断 |

核心逻辑：

- `Flow` 通过 SimPy 协程模拟传输。
- `Link` 维护当前活跃流和每个流的带宽分配。
- 多个 `Flow` 共享链路时，会触发带宽重分配。
- 正在传输的流会被 `simpy.Interrupt` 打断，然后重算剩余传输时间。

## 3. topology.py：拓扑图与路由缓存

`Topology` 继承自 `networkx.DiGraph`。

它负责：

- 保存所有网络顶点。
- 添加 `Connection`。
- 添加 `Cell` 或 `Scenario`。
- 查找最短路径。
- 生成 `Route`。
- 计算 RTT。
- 缓存路由，避免重复计算。

关键设计：

### Node 不能直接连 Node

`Topology.add_connection()` 会拒绝 `Node -> Node` 直连。

原因是：

- `Node` 是计算端点，不代表带宽资源。
- 真正承载带宽的是 `Link`。
- 如果允许 `Node -> Node`，`Flow` 找不到 `Link`，也就无法计算瓶颈带宽。

正确结构是：

```text
Node -> Link -> switch -> Link -> Node
```

### route 缓存

`Topology.route(source, destination)` 首次调用时会：

1. 计算最短路径。
2. 构造 `Route`。
3. 计算 RTT。
4. 写入 `_route_cache`。

后续调用会复用路径，但在实际使用时可以重新采样随机时延。

## 4. cell.py：组合式拓扑 DSL

`cell.py` 让用户不用手工一条条添加 `Connection`，而是像搭积木一样创建拓扑。

核心类型：

| 类型 | 含义 |
|---|---|
| `Cell` | 可物化网络单元基类 |
| `Host` | 一个 Node + 一条接入 Link |
| `Client` | 客户端 Host 快捷类 |
| `Broker` | Broker Host 快捷类 |
| `LANCell` | 多个 Host 共享一个透明 switch |
| `SharedLinkCell` | 多个 Host 共享一条瓶颈链路 |
| `GeoCell` | 按地理区域/密度重复生成子单元 |
| `UpDownLink` | 上下行非对称回传链路 |

`Cell` 的 `nodes` 可以是：

- `Node`
- `Cell`
- `Callable`
- 列表/元组等可迭代对象

这意味着你可以写出很灵活的拓扑：

```python
LANCell([
    nodes.rpi3,
    nodes.tx2,
    lambda: nodes.nuc()
])
```

这些内容会在 `materialize()` 阶段递归展开成真实拓扑。

## 5. blocks：常用构造块

### blocks.nodes

提供常见节点工厂：

- `create_vm_node()`
- `create_server_node()`
- `create_rpi3_node()`
- `create_rpi4_node()`
- `create_nuc_node()`
- `create_tx2_node()`
- `create_nano()`
- `create_nx()`
- `create_coral()`
- `create_rockpi()`

这些函数会创建带容量、架构和标签的 `Node`。

例如：

```python
from ether.blocks import nodes

server = nodes.server()
rpi = nodes.rpi3()
tx2 = nodes.tx2()
```

### blocks.cells

提供常见网络单元：

- `MobileConnection`：移动网络回传。
- `BusinessIsp`：企业 ISP 回传。
- `FiberToExchange`：光纤回传。
- `IoTComputeBox`：IoT 计算盒。
- `Cloudlet`：边缘 Cloudlet。

## 6. scenarios：完整场景

预置场景用于快速生成较完整的实验拓扑。

| 场景 | 文件 | 用途 |
|---|---|---|
| `UrbanSensingScenario` | `scenarios/urbansensing.py` | 城市感知、边缘传感器、Cloudlet |
| `IndustrialIoTScenario` | `scenarios/industrialiot.py` | 工业物联网 |
| `CloudRegionsScenario` | `scenarios/cloudregions.py` | 云区域延迟场景 |

使用方式通常是：

```python
from ether.topology import Topology
from ether.scenarios.urbansensing import UrbanSensingScenario

topology = Topology()
topology.add(UrbanSensingScenario())
```

## 7. inet：互联网/云区域延迟图

`inet` 子包保存 cloudping、gcloudping、wondernetwork 等数据源生成的 graphml 图。

主要用途：

- 加载云区域之间的延迟。
- 构建跨区域网络。
- 给云区域场景提供真实感更强的 RTT。

## 8. qos：时延分布

`qos.latency` 保存常见网络类型的延迟分布，例如：

- LAN
- mobile ISP
- business ISP

`Connection` 可以使用固定时延，也可以使用这些随机时延分布。

## 9. converter、vis、export

这些模块用于可视化和导出：

- `vis.py`：用 matplotlib 绘制拓扑。
- `converter/pyvis.py`：转为 PyVis 网络图。
- `export.py`：导出 JSON 结构。

它们不是仿真核心，但对调试拓扑很有用。

