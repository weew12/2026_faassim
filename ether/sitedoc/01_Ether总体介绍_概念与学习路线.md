# Ether 总体介绍：概念与学习路线

## 1. Ether 是什么

Ether 是一个面向边缘计算、云边协同和网络拓扑实验的轻量网络仿真库。在本项目中，它作为 faas-sim 的底层网络与拓扑建模模块存在。

简单说，Ether 负责回答三类问题：

1. 网络里有哪些节点？
2. 节点之间怎么连接？
3. 一段数据从节点 A 传到节点 B 需要多长时间？

对应到源码中：

- “有哪些节点”由 `Node`、`Capacity`、`blocks.nodes` 表达。
- “怎么连接”由 `Connection`、`Link`、`Topology`、`Cell` 表达。
- “传多久”由 `Route`、`Flow`、`Link` 的带宽分配逻辑表达。

## 2. Ether 在 faas-sim 中的位置

faas-sim 模拟 Serverless/FaaS 系统。函数运行不是孤立的，它需要：

- 节点资源：CPU、内存、架构、标签。
- 网络拓扑：边缘节点、云节点、存储节点、互联网骨干。
- 镜像传输：Docker 镜像从 registry 拉到目标节点。
- 数据传输：输入数据从存储节点下载到函数副本，输出数据上传回存储节点。
- 调度成本估计：某个函数放在哪个节点上，网络代价和资源代价不同。

这些底层能力主要来自 Ether。

可以把整体关系理解为：

```text
faas-sim
  ├─ 函数部署、调用、伸缩、指标
  ├─ Skippy 调度器
  └─ Ether
       ├─ 节点与资源
       ├─ 拓扑与路由
       ├─ 链路与带宽
       └─ 网络流传输时间
```

## 3. Ether 的核心抽象

### Node

`Node` 表示一个计算节点、存储节点或网络中的实体设备。它有：

- `name`：节点名。
- `capacity`：CPU 和内存容量。
- `arch`：CPU 架构，例如 `x86`、`aarch64`、`arm32v7`。
- `labels`：设备类型、GPU/TPU 能力、区域等标签。
- `coordinate`：可选坐标，用于距离或延迟估计。

在 faas-sim 中，`Node` 会被转成 Skippy 的调度节点。

### Capacity

`Capacity` 描述节点资源容量：

- `cpu_millis`：CPU 毫核数，1000 表示 1 核。
- `memory`：内存字节数。

使用毫核而不是直接用核数，是为了贴近 Kubernetes 的资源模型。

### Link

`Link` 表示真正承载带宽的链路。它维护：

- 标称带宽。
- 当前经过该链路的网络流。
- 每个网络流分到的带宽。
- 公平共享后的最大可分配带宽。

Ether 的重要设计是：带宽不是记录在 `Node -> Node` 边上，而是记录在 `Link` 顶点上。

### Connection

`Connection` 表示拓扑图中的一条边。它连接两个网络顶点：

- `Node`
- `Link`
- 字符串形式的透明网络顶点，例如交换机、互联网骨干

`Connection` 保存时延信息，可以是固定时延，也可以是随机时延分布。

### Topology

`Topology` 继承 `networkx.DiGraph`，负责保存节点、链路、透明顶点和连接，并提供：

- 添加连接。
- 添加场景或网络单元。
- 查询最短路径。
- 查询路由。
- 计算 RTT。
- 缓存路由结果。

### Route

`Route` 是一次从源节点到目标节点的路径结果。它包含：

- `source`
- `destination`
- `path`：完整路径顶点。
- `hops`：路径中真正的 `Link` 对象。
- `rtt`：往返时延。

`Flow` 只关心 `hops`，因为只有 `Link` 才消耗带宽。

### Flow

`Flow` 表示一次网络数据传输。它会：

1. 根据 RTT 模拟连接建立时间。
2. 把自己加入路径上的每条链路。
3. 计算当前 goodput。
4. `yield env.timeout(transmission_time)` 推进 SimPy 时间。
5. 如果其他流加入或退出导致带宽变化，通过 `simpy.Interrupt` 中断并重算剩余时间。
6. 传输完成后释放链路占用。

## 4. Ether 的学习路线

建议按下面顺序读：

1. 先理解 `core.py` 的基础类型：`Node`、`Capacity`、`Link`、`Connection`、`Route`、`Flow`。
2. 再理解 `topology.py`：拓扑图如何添加连接、如何算路径、如何缓存路由。
3. 然后看 `cell.py`：如何用 `Host`、`LANCell`、`SharedLinkCell` 组合复杂拓扑。
4. 再看 `blocks/`：常用设备和网络单元是怎么封装出来的。
5. 最后看 `scenarios/`：如何生成城市感知、工业物联网、云区域等完整实验场景。

## 5. 最小心智模型

如果只记住一张图，可以记住这个：

```text
Node -- Connection --> Link -- Connection --> switch -- Connection --> Link -- Connection --> Node
                         │                                      │
                         └──────── Flow 会消耗这里的带宽 ───────┘
```

不要把 Ether 理解为“节点之间有一条边就能传输”。Ether 的建模重点是：

- `Node` 是端点。
- `Link` 是带宽资源。
- `Connection` 是图上的连通关系。
- `Route` 是路径。
- `Flow` 是沿路径传输的数据。

