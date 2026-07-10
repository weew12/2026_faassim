# 核心概念：Node、Link、Connection、Route、Flow

## 1. Node：网络中的计算端点

`Node` 表示网络中的一个计算或存储端点。

常见节点：

- 云虚拟机
- 边缘服务器
- Raspberry Pi
- Jetson TX2/Nano/NX
- Coral TPU
- 存储节点

核心字段：

| 字段 | 含义 |
|---|---|
| `name` | 节点名 |
| `capacity` | CPU/内存容量 |
| `arch` | CPU 架构 |
| `labels` | 调度标签、设备类型、加速器能力 |
| `coordinate` | 可选坐标 |

示例：

```python
from ether.core import Node, Capacity

edge = Node(
    "edge-1",
    capacity=Capacity(cpu_millis=4000, memory=4 * 1024 * 1024 * 1024),
    arch="aarch64",
    labels={"ether.edgerun.io/type": "edge"}
)
```

## 2. Capacity：节点资源容量

`Capacity` 使用 Kubernetes 风格资源单位：

- CPU：毫核，`1000` 表示 1 核。
- 内存：字节。

例如：

```python
from ether.core import Capacity

cap = Capacity(cpu_millis=2000, memory=2 * 1024 * 1024 * 1024)
```

为什么用毫核？

因为调度系统常常需要表达小数 CPU，例如 `500m` 表示 0.5 核。用毫核能避免浮点误差，也更贴近 Kubernetes。

## 3. Link：真正承载带宽的链路

`Link` 是 Ether 网络流模型的核心。它表示有带宽上限的链路资源。

核心字段：

| 字段 | 含义 |
|---|---|
| `bandwidth` | 标称带宽，单位 Mbit/s |
| `tags` | 链路标签 |
| `allocation` | 每个活跃 Flow 分到多少带宽 |
| `num_flows` | 当前链路上的活跃流数量 |
| `max_allocatable` | 当前每个竞争流最多可获得的带宽 |

示例：

```python
from ether.core import Link

uplink = Link(bandwidth=100, tags={"type": "uplink"})
```

`Link` 的设计重点是带宽共享。多个 `Flow` 同时经过一条 `Link` 时，它们会共享这条链路的带宽。

## 4. Connection：拓扑中的边

`Connection` 表示两个网络顶点之间的一段连接。

网络顶点可以是：

- `Node`
- `Link`
- 字符串透明节点，例如 `"switch-1"`、`"internet"`

`Connection` 保存：

- `source`
- `target`
- 固定时延 `latency`
- 随机时延分布 `latency_dist`

示例：

```python
from ether.core import Connection

Connection(source=edge, target=uplink, latency=1)
```

注意：`Connection` 不是带宽资源。它只是图上的连接关系和时延信息。带宽在 `Link` 上。

## 5. 为什么不能 Node 直连 Node

Ether 强制禁止：

```python
Connection(node_a, node_b)
```

原因是 `Flow` 需要通过路径中的 `Link` 计算瓶颈带宽。如果 Node 直接连 Node，路径里没有 `Link`，网络流无法知道带宽是多少。

正确建模：

```text
Node A -> Link A -> switch -> Link B -> Node B
```

这样：

- `Node` 表示端点。
- `Link` 表示带宽。
- `switch` 只是透明转发顶点。
- `Connection` 表示它们之间的图关系。

## 6. Route：一次路径解析结果

`Route` 保存从源节点到目标节点的路径。

字段：

| 字段 | 含义 |
|---|---|
| `source` | 源节点 |
| `destination` | 目标节点 |
| `path` | 完整路径，包括 Node、Link、透明节点 |
| `hops` | 仅包含 Link 的路径 |
| `rtt` | 往返时延 |

`path` 和 `hops` 的区别很重要：

```text
path = [Node A, Link A, "switch", Link B, Node B]
hops = [Link A, Link B]
```

`Flow` 只遍历 `hops`，因为只有 Link 会消耗带宽。

## 7. Flow：一次网络传输

`Flow` 表示一段数据从源节点传到目标节点。

创建 Flow 需要：

- SimPy 环境。
- 数据大小，单位字节。
- `Route`。

示例：

```python
import simpy
from ether.core import Flow

env = simpy.Environment()
route = topology.route(source, destination)
flow = Flow(env, size=10 * 1024 * 1024, route=route)
env.process(flow.start())
env.run()
```

## 8. Flow 的时间模型

Flow 的传输过程大致如下：

```text
开始
  |
  |-- 1. 按 1.5 * RTT 模拟连接建立
  |
  |-- 2. 加入路径上的 Link
  |
  |-- 3. 所有相关链路重新分配带宽
  |
  |-- 4. 根据 goodput 计算剩余传输时间
  |
  |-- 5. env.timeout(transmission_time)
  |
  |-- 6. 如果期间带宽变化，被 Interrupt 打断并重算
  |
  |-- 7. 传输完成，释放链路
结束
```

## 9. 多流共享链路

当多个 Flow 共享同一条 Link 时：

1. 新 Flow 加入。
2. `add_and_rebalance()` 更新链路上的流数量。
3. `rebalance()` 重新计算分配。
4. 已经在传输的 Flow 被 `simpy.Interrupt` 打断。
5. 被打断的 Flow 根据已经发送的字节数和新 goodput 重算剩余时间。

这比“每隔一秒检查一次带宽”的轮询模型更精确，也更高效。

## 10. goodput 和 bandwidth

`Link.bandwidth` 是标称带宽，单位 Mbit/s。

`Link.get_goodput_bps(flow)` 会把分配到的 Mbit/s 转成 B/s，并乘以一个约 0.97 的系数模拟 TCP 开销。

因此：

```text
实际传输速度 = 分配带宽 × 125000 × 0.97
```

## 11. 读源码时的关键入口

推荐按这个顺序看 `core.py`：

1. `Node`
2. `Capacity`
3. `Link`
4. `Connection`
5. `Route`
6. `Flow.run()`
7. `add_and_rebalance()`
8. `remove_and_rebalance()`
9. `rebalance()`
10. `collect_subnet()`
