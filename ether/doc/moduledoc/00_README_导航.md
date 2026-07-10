# Ether 中文教程导航

这组文档面向想系统理解 `ether` 的读者，不按源码文件逐行展开，而是按“概念 -> 组成 -> 入门 -> 案例 -> 集成”的学习顺序组织。

`ether` 在本项目中是网络与拓扑仿真层。它负责描述云、边缘、物联网设备之间的网络结构，并用 SimPy 模拟网络流在链路上的传输时间、带宽竞争和时延。`faas-sim` 在函数镜像拉取、数据下载/上传、节点拓扑、调度成本估计等地方都会依赖 Ether。

## 推荐阅读顺序

1. [01_Ether总体介绍_概念与学习路线.md](01_Ether总体介绍_概念与学习路线.md)
2. [02_Ether组成与源码地图.md](02_Ether组成与源码地图.md)
3. [03_核心概念_Node_Link_Connection_Route_Flow.md](03_核心概念_Node_Link_Connection_Route_Flow.md)
4. [04_拓扑建模_Topology_Cell_Blocks_Scenarios.md](04_拓扑建模_Topology_Cell_Blocks_Scenarios.md)
5. [05_入门案例_从最小拓扑到网络流仿真.md](05_入门案例_从最小拓扑到网络流仿真.md)
6. [06_进阶案例_预置场景_共享链路_云区域延迟.md](06_进阶案例_预置场景_共享链路_云区域延迟.md)
7. [07_Ether与faas-sim集成.md](07_Ether与faas-sim集成.md)

## 这组文档覆盖什么

- Ether 是什么，解决什么问题。
- Ether 的节点、容量、链路、连接、路由、网络流模型。
- Topology 为什么基于 `networkx.DiGraph`，为什么不允许 Node 直连 Node。
- `Cell`、`Host`、`LANCell`、`SharedLinkCell`、`GeoCell` 的组合式拓扑 DSL。
- `blocks` 中常见云边设备与网络单元。
- `scenarios` 中城市感知、工业物联网、云区域场景。
- `Flow` 如何基于 SimPy 推进时间，如何在多流并发时重新分配带宽。
- Ether 如何与 faas-sim 的 Docker 镜像拉取、数据传输、Skippy 调度适配协作。

## 这组文档不覆盖什么

- 不逐行重复 `ether/doc` 中已经有的源码文件级说明。
- 不翻译官方站点。
- 不改 Ether 源码逻辑。

