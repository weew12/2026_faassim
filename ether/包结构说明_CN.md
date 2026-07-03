# ether 内置子包结构说明

`ether` 是本次合入 faas-sim 的本地网络仿真子包，用来替换原先通过 `edgerun-ether` 安装获得的外部依赖。faas-sim 原有 `import ether...` 语句保持不变，但解析目标变为项目根目录下的本地 `ether` 包。

## 核心结构

- `core.py`：定义 Node、Capacity、Connection、Route、Flow、Link 以及带宽重分配逻辑，是网络流仿真的核心。
- `topology.py`：继承 `networkx.DiGraph`，负责拓扑图、连接、最短路径路由和 RTT 计算。
- `cell.py`：提供 Host、LANCell、SharedLinkCell、GeoCell 等组合式拓扑单元。
- `blocks/`：提供常见硬件节点和网络单元构造函数。
- `scenarios/`：提供城市感知、工业物联网、云区域等预置场景。
- `inet/`：保存并加载互联网区域延迟图，支持 cloudping、gcloudping、wondernetwork 数据。
- `qos/`：保存局域网、移动网络、企业网络等时延分布。
- `converter/`、`vis.py`、`export.py`：提供拓扑可视化和导出辅助能力。

## 与 faas-sim 的关系

faas-sim 中的 `sim/topology.py`、`sim/net.py`、`sim/docker.py`、`sim/faas/*` 和 `ext/raith21/*` 通过 Ether 提供的 Node、Link、Topology、Flow、Route 等对象完成节点建模、镜像拉取、链路传输和网络拓扑查询。本地内置后，实验代码不再依赖外部 `edgerun-ether` 包版本。
