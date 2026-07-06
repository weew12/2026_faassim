# 10 · blocks 预置构造块

> 本文档解析 `ether/blocks/` 子包(3 个文件,共 ~400 行),提供"工厂模式"封装好的预置设备、主机和网络单元。
>
> **核心内容**:`nodes.py`(11 种设备工厂) + `hosts.py`(Configurator 模式) + `cells.py`(3 种回传 + Cloudlet)

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 2 | 包入口(空 docstring) |
| `nodes.py` | 231 | 11 种预置设备工厂(VM/server/RPI3/4/NUC/Coral/Jetson TX2/Nano/NX/RockPi) |
| `hosts.py` | 75 | Configurator 模式(函数式配置器) |
| `cells.py` | 94 | 3 种 UpDownLink 子类(MobileConnection/BusinessIsp/FiberToExchange) + IoTComputeBox + Cloudlet |

**全局约定**:`counters = defaultdict(lambda: itertools.count(0, 1))` —— 设备名唯一。

## 2. `nodes.py` —— 11 种预置设备工厂

### 设备清单

| 工厂 | 用途 | CPU | 内存 | 架构 | 关键 labels |
|---|---|---|---|---|---|
| `create_vm_node` | 云虚拟机 | 4 | 8GB | x86 | `type=vm, model=vm` |
| `create_server_node` | 高规格服务器 | 88 | 188GB | x86 | `type=server, model=server` |
| `create_rpi3_node` | 树莓派 3 | 4 | 1GB | arm32 | `type=sbc, model=rpi3b+` |
| `create_rpi4_node` | 树莓派 4 | 4 | 1GB | arm32v7 | `type=sbc, model=rpi4` |
| `create_rockpi` | RockPi 4 | 6 | 4GB | aarch64 | `type=sbc, model=rockpi4` |
| `create_nuc_node` | Intel NUC | 4 | 16GB | x86 | `type=sffc, model=nuci5` |
| `create_coral` | Coral Dev Board | 4 | 1GB | aarch64 | `type=sbc, capabilities/tpu=edgetpu` |
| `create_tx2_node` | Jetson TX2 | 4 | 8GB | aarch64 | `type=embai, capabilities/cuda=10, gpu=pascal` |
| `create_nano` | Jetson Nano | 4 | 4GB | aarch64 | `type=embai, capabilities/cuda=10, gpu=maxwell` |
| `create_nx` | Jetson Xavier NX | 6 | 8GB | aarch64 | `type=embai, capabilities/cuda=10, gpu=volta` |

### 核心函数 `create_node`

```python
def create_node(name, cpus, mem, arch, labels) -> Node:
    capacity = Capacity(cpu_millis=cpus * 1000, memory=parse_size_string(mem))
    return Node(name, capacity=capacity, arch=arch, labels=labels)
```

所有工厂都是这个函数的"特化",调对应参数即可。

### 别名

文件底部给工厂起别名方便 import:

```python
rpi3 = create_rpi3_node
nuc = create_nuc_node
tx2 = create_tx2_node
server = create_server_node
nx = create_nx
nano = create_nano
coral = create_coral
rpi4 = create_rpi4_node
rockpi = create_rockpi
```

### 典型用法

```python
from ether.blocks import nodes

# 创建节点
rpi = nodes.rpi3()    # 树莓派 3,1GB 内存
tx2 = nodes.tx2()     # Jetson TX2,8GB,带 CUDA/GPU
gpu_node = nodes.nx()  # Jetson Xavier NX,带 Volta GPU

# 装进 Cell
LANCell([rpi, rpi, rpi, tx2], backhaul=...)
```

### 对论文的用处

| 论文实验要素 | `nodes.py` 提供的接口 |
|---|---|
| **节点异构性** | 11 种设备,核数 4-88,内存 1GB-188GB |
| **镜像架构约束** | `arch` 字段(arm32/aarch64/x86) |
| **GPU/TPU 调度** | `labels['ether.edgerun.io/capabilities/cuda']` / `gpu` / `tpu` |
| **调度能力过滤** | `labels['ether.edgerun.io/type']`(vm/server/sbc/sffc/embai) |
| **设备型号** | `labels['ether.edgerun.io/model']` |

**论文中如何用**:

- 做"异构边缘"实验,直接混用 rpi3 + tx2 + nx + server
- 调度时按 `node.arch` 过滤镜像,按 `node.labels['.../cuda']` 选 GPU 任务

## 3. `hosts.py` —— Configurator 模式

### 核心抽象

```python
Configurator = Callable[[Host], None]   # 配置函数类型
```

### 三个工具函数

```python
def node_name(the_name: str) -> Configurator:
    """返回一个 configurator,设 host.node.name = the_name"""
    def cfg(host):
        host.nodes[0].name = the_name
    return cfg

def as_host(node, *configurators) -> Host:
    """把 node 包成 Host,按顺序应用 configurators"""
    host = Host(node)
    for cfg in configurators:
        cfg(host)
    return host

def create_host(*configurators):
    """创建一个匿名 Node,返回包好的 Host"""
    return as_host(Node(''), *configurators)
```

### 设计要点

**函数式 Builder** —— 用 `*configurators` 链式调,替代构造参数爆炸。

```python
# 链式配置
host = as_host(
    nodes.rpi3(),
    node_name('sensor_42'),
    set_linkname,
    add_label('role', 'sensor')
)
```

**对比继承 + super 的写法**:

```python
class MyHost(Host):
    def __init__(self):
        super().__init__(...)
        self.node.name = 'foo'
        self.link.tags['name'] = ...
```

函数式更灵活,易组合,易扩展。

### `main()` 测试函数

文件还提供了演示用法:

```python
def set_hostname_foo(host): host.node.name = 'foo'
def set_linkname(host):
    host.link.tags['name'] = 'link_%s' % host.node.name
    host.link.tags['hostname'] = host.node.name

h = create_host(set_hostname_foo, set_linkname)
```

### 对论文的用处

- 自定义节点配置(批量命名、加特定 label、设 link tag)用 Configurator 模式
- 比继承 Host 子类更轻量

## 4. `cells.py` —— 回传 + Cloudlet

### 3 种 `UpDownLink` 子类(回传配置)

| 类 | 下行/上行 (Mbit/s) | 时延分布 | 场景 |
|---|---|---|---|
| `MobileConnection` | 125 / 25 | `latency.mobile_isp` | 移动 4G/5G(典型非对称) |
| `BusinessIsp` | 500 / 50 | `latency.business_isp` | 企业宽带 |
| `FiberToExchange` | 1000 / 1000 | `latency.lan` | 光纤到机房(对称高速) |

```python
class MobileConnection(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(125, 25, backhaul, latency.mobile_isp)

class BusinessIsp(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(500, 50, backhaul, latency.business_isp)

class FiberToExchange(UpDownLink):
    def __init__(self, backhaul='internet'):
        super().__init__(1000, 1000, backhaul, latency.lan)
```

### `IoTComputeBox(LANCell)` (53-55)

```python
class IoTComputeBox(LANCell):
    pass
```

**空 `pass`,纯语义化别名** —— 表达"这个 LANCell 专门用于 IoT 现场计算设备"。

### `Cloudlet(LANCell)` (58-94)

```python
class Cloudlet(LANCell):
    def __init__(self, server_per_rack=5, racks=1, backhaul=None):
        self.racks = racks
        self.server_per_rack = server_per_rack
        nodes = [self._create_rack] * racks
        super().__init__(nodes, backhaul=backhaul)

    def _create_identity(self):
        self.nr = next(counters['cloudlet'])
        self.name = 'cloudlet_%d' % self.nr
        self.switch = 'switch_%s' % self.name

    def _create_rack(self):
        return LANCell([create_server_node] * self.server_per_rack, backhaul=self.switch)
```

**Cloudlet = N 个 rack,每个 rack = M 个 server_node**。结构:

```
Cloudlet
├── rack_0 = LANCell([server, server, server, server, server], backhaul=switch)
├── rack_1 = LANCell([server, ...])
└── switch_cloudlet_X  ← 所有 rack 共享的交换机
```

**`[self._create_rack] * racks`** 是"方法引用 × 次数"模式:

- `materialize` 时调 N 次 `_create_rack()`
- 每次新建一个 rack
- `self.switch` 在 `_create_identity` 里设置,所有 rack 共享

### 典型用法

```python
from ether.blocks.cells import Cloudlet, MobileConnection, BusinessIsp, FiberToExchange, IoTComputeBox

# 移动 4G/5G 上联
iot_box = IoTComputeBox([nodes.rpi3, nodes.nuc], backhaul=MobileConnection('internet'))

# 企业 ISP 上联
factory = LANCell([iot_box], backhaul=BusinessIsp('internet'))

# 光纤上联的边缘 Cloudlet
edge = Cloudlet(server_per_rack=10, racks=3, backhaul=FiberToExchange('internet'))
```

### 对论文的用处

| 论文实验要素 | `cells.py` 提供的接口 |
|---|---|
| **移动 4G/5G 回传** | `MobileConnection(backhaul='internet')` |
| **企业 ISP 回传** | `BusinessIsp(backhaul='internet')` |
| **光纤到机房** | `FiberToExchange(backhaul='internet')` |
| **IoT 现场计算** | `IoTComputeBox([...], backhaul=...)` |
| **机架式 Cloudlet** | `Cloudlet(server_per_rack, racks, backhaul)` |
| **自定义回传** | 继承 `UpDownLink` 自定义 bw_down/bw_up/latency_dist |

## 5. blocks/ 三件套关系

```
blocks/
├── nodes.py   ← 设备工厂(裸 Node)
├── hosts.py   ← Host 配置(给 Node 加 link、set name 等)
└── cells.py   ← 网络单元工厂(回传 + Cloudlet)
```

**典型组合**:

```python
# 单设备
host = Host(nodes.rpi3())

# 同类设备集
box = IoTComputeBox([nodes.rpi3, nodes.rpi3, nodes.nuc])

# 多机架 Cloudlet
cloud = Cloudlet(server_per_rack=5, racks=3)

# 复合单元
LANCell(
    nodes=[IoTComputeBox([nodes.nuc, nodes.tx2]), SharedLinkCell([nodes.rpi3] * 5)],
    backhaul=BusinessIsp('internet')
)
```
