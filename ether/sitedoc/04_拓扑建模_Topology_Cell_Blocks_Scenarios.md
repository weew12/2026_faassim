# 拓扑建模：Topology、Cell、Blocks、Scenarios

## 1. Topology 是什么

`Topology` 是 Ether 中保存网络结构的图对象。它继承 `networkx.DiGraph`，所以本质上是一个有向图。

它保存：

- `Node`
- `Link`
- 字符串透明节点
- `Connection`

并提供：

- 添加连接。
- 添加 Cell。
- 添加 Scenario。
- 查找最短路径。
- 生成 Route。
- 计算 RTT。
- 缓存路由。

## 2. 最小拓扑结构

Ether 不允许 Node 直接连接 Node，因此最小可传输拓扑通常长这样：

```text
node_a -> link_a -> switch -> link_b -> node_b
```

代码结构：

```python
from ether.core import Node, Link, Connection
from ether.topology import Topology

topology = Topology()

a = Node("a")
b = Node("b")
link_a = Link(100, tags={"name": "a-uplink"})
link_b = Link(100, tags={"name": "b-uplink"})
switch = "switch"

topology.add_connection(Connection(a, link_a))
topology.add_connection(Connection(link_a, switch))
topology.add_connection(Connection(switch, link_b))
topology.add_connection(Connection(link_b, b))
```

## 3. add_connection()

`Topology.add_connection(connection, directed=False)` 会把连接加入图。

默认 `directed=False`，表示添加双向边：

```python
topology.add_connection(Connection(a, link_a))
```

等价于：

```text
a -> link_a
link_a -> a
```

如果 `directed=True`，则只添加单向边。

## 4. route()

`topology.route(source, destination)` 返回 `Route`。

内部过程：

1. 检查 `_route_cache`。
2. 如果没有缓存，调用 `networkx.shortest_path()` 找路径。
3. 构造 `Route`。
4. 计算 RTT。
5. 写入缓存。
6. 返回路由副本。

示例：

```python
route = topology.route(a, b)
print(route.path)
print(route.hops)
print(route.rtt)
```

## 5. latency()

`topology.latency(source, destination)` 返回单向时延。

默认逻辑：

```text
latency = route.rtt / 2
```

也可以使用坐标距离：

```python
topology.latency(a, b, use_coordinates=True)
```

坐标模式不查拓扑路径，适合大规模粗略估计。

## 6. Cell：组合式拓扑 DSL

手工添加每条 `Connection` 很繁琐。`Cell` 提供了更高层的拓扑构造方式。

核心思想：

```text
Cell 是可以被 materialize 到 Topology 里的网络单元。
```

也就是说：

```python
cell.materialize(topology)
```

会把这个网络单元展开成一组节点、链路和连接。

## 7. Host

`Host` 表示一个计算节点加一条接入链路。

结构：

```text
Node -> Link -> backhaul
```

示例：

```python
from ether.cell import Host
from ether.blocks import nodes

host = Host(nodes.rpi3(), link_bw=100)
topology = host.generate()
```

## 8. LANCell

`LANCell` 表示多个 Host 共享一个内部 switch。

结构：

```text
node_1 -> link_1 -> switch
node_2 -> link_2 -> switch
node_3 -> link_3 -> switch
```

适合模拟：

- 机房内部网络
- 小型边缘集群
- 多台设备接入同一个局域网

示例：

```python
from ether.cell import LANCell
from ether.blocks import nodes

lan = LANCell([
    nodes.rpi3,
    nodes.nuc,
    nodes.tx2
])

topology = lan.generate()
```

## 9. SharedLinkCell

`SharedLinkCell` 表示多个节点共享一条瓶颈链路。

结构：

```text
node_1 -> local_link -> shared_link -> backhaul
node_2 -> local_link -> shared_link -> backhaul
node_3 -> local_link -> shared_link -> backhaul
```

适合模拟：

- 多个边缘设备共享一个 4G/5G 回传。
- 多个传感器共享一个网关出口。
- 多台设备共享一条上行链路。

## 10. GeoCell

`GeoCell` 用于重复生成地理区域。

你可以理解为：

```text
生成 N 个小区，每个小区内部再生成若干节点。
```

`density` 可以是固定值，也可以是随机采样器。

适合模拟：

- 城市多个街区。
- 工业园多个区域。
- 多个边缘接入点。

## 11. UpDownLink

`UpDownLink` 表示上下行带宽不一样的回传链路。

字段：

- `bw_down`
- `bw_up`
- `backhaul`
- `latency_dist`

移动网络、企业 ISP、光纤回传都可以用它建模。

## 12. blocks.nodes

`blocks.nodes` 是常用设备工厂。

常见函数：

```python
from ether.blocks import nodes

nodes.server()
nodes.rpi3()
nodes.rpi4()
nodes.nuc()
nodes.tx2()
nodes.nano()
nodes.nx()
nodes.coral()
nodes.rockpi()
```

每个函数都会返回一个带容量、架构和标签的 `Node`。

## 13. blocks.cells

`blocks.cells` 是常用网络单元：

```python
from ether.blocks.cells import MobileConnection, BusinessIsp, FiberToExchange, Cloudlet, IoTComputeBox
```

常见用途：

- `MobileConnection`：移动回传。
- `BusinessIsp`：企业网络。
- `FiberToExchange`：高速光纤。
- `Cloudlet`：边缘云资源池。
- `IoTComputeBox`：IoT 现场计算盒。

## 14. scenarios

`scenarios` 是完整拓扑场景。

### UrbanSensingScenario

城市感知场景，包括：

- 多个城市小区。
- Raspberry Pi 传感器。
- NUC/TX2 近端计算资源。
- 移动回传。
- 城市级 Cloudlet。

### IndustrialIoTScenario

工业物联网场景，包括工厂、传感设备、边缘计算资源、企业网络等。

### CloudRegionsScenario

云区域场景，结合互联网延迟图，适合模拟跨云区域通信。

## 15. 建模选择建议

| 目标 | 推荐方式 |
|---|---|
| 学习最小网络结构 | 手工创建 `Node`、`Link`、`Connection` |
| 搭小型局域网 | `LANCell` |
| 模拟共享瓶颈链路 | `SharedLinkCell` |
| 模拟城市/区域重复结构 | `GeoCell` |
| 快速使用常见设备 | `blocks.nodes` |
| 快速生成完整实验环境 | `scenarios` |

