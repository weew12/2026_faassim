# 11 · scenarios 预置场景

> 本文档解析 `ether/scenarios/` 子包(3 个文件,共 156 行),提供 3 个真实研究场景的"开箱即用"模板。
>
> **核心内容**:`CloudRegionsScenario`(多云区域)+ `IndustrialIoTScenario`(工业 IoT) + `UrbanSensingScenario`(城市感知)

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 2 | 包入口(空 docstring) |
| `cloudregions.py` | 31 | 多云区域场景 |
| `industrialiot.py` | 48 | 工业 IoT 场景 |
| `urbansensing.py` | 77 | 城市感知场景(Array of Things 思路) |

## 2. `CloudRegionsScenario` —— 多云区域

```python
class CloudRegionsScenario:
    def __init__(self, regions: List[str], region_size: List[Tuple[int, int]]):
        self.regions = regions          # 云区域名列表,如 ['us-east-1', 'eu-west-1']
        self.region_size = region_size  # 每个区域的 Cloudlet 规模,如 [(5, 2), (5, 2)]

    def materialize(self, topology: Topology):
        for i in range(len(self.regions)):
            size = self.region_size[i]
            Cloudlet(*size, backhaul=self.regions[i]).materialize(topology)
```

### 思路

对每个选中的云区域名(如 `us-east-1`),建一个 `Cloudlet`,**backhaul = 云区域名**。

**这些 backhaul 节点已经在 `inet/graphs/` 加载的真实互联网延迟图里**:

- `cloudping_*.graphml`:AWS 区域
- `gcloudping_*.graphml`:GCP 区域
- `wondernetwork_*.graphml`:更广

所以这个场景自动接入了**真实区域间 RTT**(不是模拟值)。

### 用法

```python
from ether.scenarios.cloudregions import CloudRegionsScenario
from ether.topology import Topology

t = Topology()
t.add(CloudRegionsScenario(
    regions=['us-east-1', 'eu-west-1', 'ap-southeast-1'],
    region_size=[(5, 2), (5, 2), (5, 2)]   # 3 个区域,各 5×2 server
))
t.load_inet_graph('cloudping')   # 加载真实云区域延迟

# 跨区域 RTT 查询
rtt = t.route(node_in_us, node_in_eu).rtt   # 真实测量值
```

### 对论文的用处

- **多区域调度实验**(跨大洲函数调用)
- 自动接入真实 RTT 数据,论文里"区域间延迟"用 cloudping 实测,不需要自己建模

## 3. `IndustrialIoTScenario` —— 工业 IoT

```python
default_num_cells = 1
default_cell_density = ConstantSampler(10)

class IndustrialIoTScenario:
    def __init__(self, num_premises=default_num_cells,
                 premises_density=default_cell_density,
                 internet='internet'):
        self.num_premises = num_premises
        self.premises_density = premises_density
        self.internet = internet

    def materialize(self, topology: Topology):
        for _ in range(self.num_premises):
            floor_compute = IoTComputeBox(nodes=[nodes.nuc, nodes.tx2])
            floor_iot = SharedLinkCell(nodes=[nodes.rpi3] * 3)

            factory = LANCell([floor_compute, floor_iot],
                              backhaul=BusinessIsp(self.internet))
            factory.materialize(topology)

            cloudlet = Cloudlet(5, 3,
                                backhaul=UpDownLink(10000, 10000, backhaul=factory.switch))
            cloudlet.materialize(topology)
```

### 思路

**每个工厂**:

```
floor_compute = IoTComputeBox([NUC, Jetson TX2])    # 边缘计算设备
floor_iot = SharedLinkCell(3 × RPI3)                # 3 个传感器共享带宽
factory = LANCell(以上, BusinessIsp)                 # 厂内 LAN + 企业 ISP 上联
+ cloudlet = Cloudlet(5×3 server, 10G 对称光纤到 factory.switch)  # 厂间云端聚合
```

**结构图**:

```
Internet
  │
  │ BusinessIsp (企业 ISP)
  │
factory.switch
  │
  ├─── floor_compute (LANCell)
  │     ├── NUC          (Intel NUC,16GB)
  │     └── Jetson TX2   (aarch64,8GB,CUDA 10 + Pascal GPU)
  │
  └─── floor_iot (SharedLinkCell, 共享带宽)
        ├── RPI3 (1GB)
        ├── RPI3 (1GB)
        └── RPI3 (1GB)

Fiber 10G 对称 ──── cloudlet.switch
                       │
                       ├── rack_0 = LANCell([server × 5])
                       ├── rack_1 = LANCell([server × 5])
                       └── rack_2 = LANCell([server × 5])
```

**典型工业 IoT 三层架构**:厂内边缘计算 + 厂间云端聚合。

### 用法

```python
from ether.scenarios.industrialiot import IndustrialIoTScenario

t = Topology()
t.add(IndustrialIoTScenario(num_premises=3))   # 3 个工厂
```

### 对论文的用处

- **工厂边缘 + 云端聚合** 场景
- 模拟"厂内实时计算 + 厂间批量同步"
- 三层架构(传感器→边缘→云)清晰

## 4. `UrbanSensingScenario` —— 城市感知(Array of Things 思路)

```python
default_num_cells = 3
default_cloudlet_size = (5, 2)
default_cell_density = ParameterizedDistribution.lognorm((0.82, 2.02))

class UrbanSensingScenario:
    def __init__(self, num_cells=default_num_cells,
                 cell_density=default_cell_density,
                 cloudlet_size=default_cloudlet_size,
                 internet='internet'):
        self.num_cells = num_cells
        self.cell_density = cell_density
        self.cloudlet_size = cloudlet_size
        self.internet = internet

    def materialize(self, topology: Topology):
        topology.add(self.create_city())
        topology.add(self.create_cloudlet())

    def create_city(self) -> GeoCell:
        aot_node = IoTComputeBox(nodes=[nodes.rpi3, nodes.rpi3])

        neighborhood = lambda size: SharedLinkCell(
            nodes=[
                [aot_node] * size,                                # N 个 AOT 节点
                IoTComputeBox([nodes.nuc] + ([nodes.tx2] * size * 2))  # 1 NUC + 2N TX2
            ],
            shared_bandwidth=500,
            backhaul=MobileConnection(self.internet)
        )

        return GeoCell(self.num_cells, nodes=[neighborhood], density=self.cell_density)

    def create_cloudlet(self) -> Cloudlet:
        return Cloudlet(*self.cloudlet_size, backhaul=FiberToExchange(self.internet))
```

### 思路

```
城市 = GeoCell(3 cells, density=lognorm(0.82, 2.02))
每个城区 = SharedLinkCell
  ├── N × IoTComputeBox(RPI3, RPI3)            # AOT 节点(N 从对数正态采样)
  ├── IoTComputeBox(NUC + 2N × TX2)            # 近端计算盒
  ├── 500 Mbit/s 共享带宽
  └── MobileConnection 上联

+ city cloudlet = Cloudlet(5×2 server, FiberToExchange)
```

**关键技巧**:

- `default_cell_density = lognorm((0.82, 2.02))` —— 用对数正态分布生成每城区节点数,**不是固定值**
- `lambda size: SharedLinkCell(...)` —— `size` 由 GeoCell 注入(对应 `density.sample()` 的返回值)
- `IoTComputeBox([nodes.nuc] + ([nodes.tx2] * size * 2))` —— 1 个 NUC + 2N 个 TX2,**近端计算资源跟节点数成比例**

### 结构图

```
Internet
  │
  ├── MobileConnection (125/25 Mbit/s, mobile_isp 时延)
  │
  ├─── Neighborhood_0 (SharedLinkCell, 500M)
  │     ├── AOT_0  (RPI3 + RPI3)
  │     ├── AOT_1  (RPI3 + RPI3)
  │     ├── ... (n_0 个 AOT,n_0 ~ lognorm(0.82, 2.02))
  │     └── NUC + 2*n_0 个 TX2
  │
  ├─── Neighborhood_1 (同上)
  │     ...
  └─── Neighborhood_2 (同上)

FiberToExchange (1000/1000 Mbit/s, lan 时延)
  │
  └─── City Cloudlet (5×2 server)
        ├── rack_0 = LANCell([server × 5])
        └── rack_1 = LANCell([server × 5])
```

**Array of Things 思路**:每个城市角落布 RPI3 传感器,通过移动回传聚合到 Cloudlet。

### 用法

```python
from ether.scenarios.urbansensing import UrbanSensingScenario

t = Topology()
t.add(UrbanSensingScenario(
    num_cells=5,                    # 5 个城区
    cloudlet_size=(10, 3)           # Cloudlet 规模 10×3 server
))
```

### 对论文的用处

- **非固定规模边缘场景** 的标准做法(`GeoCell` + 真实分布)
- **移动回传** 场景(`MobileConnection` 模拟 5G/4G)
- 城区节点数从分布采样,贴近现实(不是固定值)
- 实验可调节 `num_cells` / `cell_density` / `cloudlet_size` 做多组对比

## 5. 三个场景的对比

| 场景 | 规模 | 节点类型 | 回传 | 异构性 | 论文价值 |
|---|---|---|---|---|---|
| **CloudRegions** | 大(跨大洲) | 全是 server(Cloudlet) | 互联网图(cloudping) | 弱 | 多区域调度、跨区域 RTT |
| **IndustrialIoT** | 中(几个厂) | NUC + TX2 + RPI3 + server | 企业 ISP + 10G 光纤 | 强 | 工厂边缘、云边协同 |
| **UrbanSensing** | 大(多个城区) | NUC + TX2 + RPI3 + server | MobileConnection + 光纤 | 强 | 城市感知、移动边缘 |

## 6. 三个场景的共性

| 共性 | 体现 |
|---|---|
| 用 Cell DSL 拼装 | `LANCell` / `SharedLinkCell` / `GeoCell` / `IoTComputeBox` / `Cloudlet` |
| 接入互联网 | 通过 `backhaul='internet'` 字符串,后由 `load_inet_graph` 注入真实延迟 |
| 异构设备 | 混用 rpi3 / nuc / tx2 / server / coral / nx |
| 多层架构 | 客户端 → 接入层 → 边缘层 → 云层 |

## 7. 对论文的接口清单

| 论文实验要素 | scenarios 提供的接口 |
|---|---|
| **多区域调度** | `CloudRegionsScenario(['us-east-1', 'eu-west-1'], [(5,2), (5,2)])` |
| **工厂边缘 + 云端聚合** | `IndustrialIoTScenario(num_premises=3)` |
| **城市感知 + 移动回传** | `UrbanSensingScenario(num_cells=5)` |
| **可调节规模** | `num_cells` / `num_premises` / `cell_density` / `cloudlet_size` |
| **自定义场景** | 继承 `CloudRegionsScenario` / `IndustrialIoTScenario` / `UrbanSensingScenario`,重写 `materialize` |

### 典型论文实验设置

```python
# 1. 选场景
t = Topology()
t.add(IndustrialIoTScenario(num_premises=5))   # 5 个工厂
t.load_inet_graph('cloudping')                 # 加载真实云区域延迟

# 2. 在此基础上自定义(添加 broker、添加额外 sensor)
from ether.blocks.cells import IoTComputeBox
from ether.blocks import nodes
t.add(IoTComputeBox([nodes.tx2] * 10))         # 添加 10 个 GPU 节点

# 3. 仿真
# ... 跑调度、跑网络传输、统计 RTT、统计带宽争抢 ...
```
