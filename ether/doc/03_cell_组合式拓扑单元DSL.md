# 03 · cell 组合式拓扑单元 DSL

> 本文档解析 `ether/cell.py`(372 行,8 个类),这是 ether 的"组合式拓扑单元 DSL"—— 让你像搭积木一样拼出真实边缘网络。
>
> **核心内容**:UpDownLink / Cell(基类)/ Host / Client / Broker / LANCell / SharedLinkCell / GeoCell

## 1. 文件概览

| 项 | 值 |
|---|---|
| 行数 | 372 |
| 导入 | `inspect`、`itertools`、`defaultdict`、`Iterable`、`Callable`、`Union`;`srds`;`ether.qos.latency`;`ether.core.{Node, Link, NetworkNode}`;`ether.topology.{Topology, Connection}` |
| 全局状态 | `counters = defaultdict(lambda: itertools.count(0, 1))` —— 按类型维护递增计数器,保证 Cell 名字唯一 |
| 类数 | 8(UpDownLink、Cell、Host、Client、Broker、LANCell、SharedLinkCell、GeoCell) |
| 角色 | **Layer 2** —— 在 core.py 之上提供"拓扑搭建 DSL" |

## 2. `UpDownLink` (19-48) —— 上下行非对称回传配置

```python
class UpDownLink:
    bw_down: int          # 下行带宽,单位 Mbit/s
    bw_up: int            # 上行带宽,单位 Mbit/s
    backhaul: NetworkNode # 上级回传目标
    latency_dist: ParameterizedDistribution  # 时延分布

    def __init__(self, bw_down, bw_up=None, backhaul='internet', latency_dist=None):
        self.bw_down = bw_down
        self.bw_up = bw_up if bw_up is not None else bw_down  # 默认 = 下行
        self.backhaul = backhaul
        self.latency_dist = latency_dist
```

| 字段 | 含义 |
|---|---|
| `bw_down` | 下行带宽(Mbit/s) |
| `bw_up` | 上行带宽(Mbit/s),默认 = `bw_down` |
| `backhaul` | 上级网络/互联网骨干,可以是节点名或 NetworkNode |
| `latency_dist` | `ParameterizedDistribution`,可来自 `ether.qos.latency` |

**意义**:**模拟真实网络"下行带宽高、上行带宽受限"的非对称场景**(光纤到户、4G/5G 都是这种)。

### 典型用法

```python
# 移动 4G/5G:下行 1000M,上行 100M
mobile = UpDownLink(bw_down=1000, bw_up=100, backhaul='internet',
                    latency_dist=latency.mobile_isp)
```

## 3. `Cell` (51-128) —— 可组合网络单元基类

### 字段

| 字段 | 含义 |
|---|---|
| `nodes` | 当前单元包含的子节点/子单元/节点工厂(可含 Node / Cell / Callable) |
| `size` | GeoCell 专用 —— 生成多少个地理单元 |
| `entropy` | 拓扑生成随机性参数(扩展预留) |
| `backhaul` | 上级回传配置 |

### 关键方法

**`materialize(topology, parent) -> None`** —— **抽象方法**,子类必须实现,把当前 Cell 展开到 topology。

**`generate() -> Topology`**:

```python
def generate(self) -> Topology:
    t = Topology()
    self.materialize(t)
    return t
```

**模板方法**:创建新 Topology + 调用 materialize(给自己用)。

**`_materialize(topology, c, backhaul)`** —— 核心递归,处理 **4 种输入**:

```python
def _materialize(self, topology, c, backhaul=None):
    if isinstance(c, Iterable):                          # 1) Iterable → 递归每个元素
        for elem in c:
            self._materialize(topology, elem, backhaul)
        return

    if callable(c):                                     # 2) callable → 调用工厂函数
        c = c()  # 工厂目前不透传额外参数

    if isinstance(c, Node):                             # 3) Node → 包成 Host
        c = Host(c, backhaul=backhaul)
    elif isinstance(c, Cell):                           # 4) Cell → 继承 backhaul
        if backhaul:
            c.backhaul = backhaul

    c.materialize(topology, self)                       # 最终展开
```

### 设计要点

**Composite + Factory 模式**:支持任意嵌套的拓扑描述。

```python
LANCell(
    nodes=[raspberry_pi_factory, fixed_basestation_factory, another_lan],
    backhaul=UpDownLink(bw_down=1000, bw_up=100, backhaul='internet')
)
```

- `nodes` 可以是节点、节点工厂、其他 Cell、列表
- 任意嵌套,统一展开

## 4. `Host` (130-184) —— 单主机单元

```python
class Host(Cell):
    node: Node
    link: Link

    def __init__(self, node, link_bw=1000, backhaul=None):
        super().__init__(nodes=[node], backhaul=backhaul)
        self.node = node
        self.link_bw = link_bw
        self.link = Link(bandwidth=self.link_bw,
                         tags={'name': 'link_%s' % node.name, 'type': 'node'})

    def materialize(self, topology, parent=None, latency_dist=latency.lan):
        node = self.nodes[0]
        topology.add_connection(Connection(node, self.link, latency_dist=latency_dist))
        if self.backhaul:
            topology.add_connection(Connection(self.link, self.backhaul))
```

| 字段 | 含义 |
|---|---|
| `node` | 封装的计算节点 |
| `link_bw` | Host 到本地接入链路的带宽(默认 **1000 Mbit/s**) |
| `link` | 内部创建的接入 Link |

**`materialize`**:

- 加 `Connection(node, self.link, latency_dist=latency.lan)` —— Node → 本地 Link,默认 LAN 时延
- 有 backhaul 时再 `Connection(self.link, self.backhaul)`

**最简单单元**:`Host = 1 Node + 1 Link`,适合单设备场景。

## 5. `Client` / `Broker` (186-207) —— Host 的语法糖

```python
class Client(Host):
    def __init__(self, name: str, **kwargs):
        super().__init__(Node(name), **kwargs)

class Broker(Host):
    def __init__(self, name: str, **kwargs):
        super().__init__(Node(name), **kwargs)
```

| 类 | 用途 | 例子 |
|---|---|---|
| `Client` | 客户端主机快捷类型(产生请求/访问服务) | `Client('user_42')` |
| `Broker` | 消息代理主机快捷类型(MQTT 等中间件) | `Broker('mqtt_broker_1')` |

**一行创建用户节点**:`Client('user_42')` 等价于 `Host(Node('user_42'))`。

## 6. `LANCell` (210-266) —— 局域网单元

### 核心机制

**`_create_identity()`**:

```python
def _create_identity(self):
    self.nr = next(counters['lan'])
    self.name = 'lan_%d' % self.nr
    self.switch = 'switch_%s' % self.name
```

**关键:内部用字符串 `'switch_lan_%d'` 作为透明交换机顶点** —— 这就是 `core.py` 里 `TransparentLink` 的用途。

### `materialize`

```python
def materialize(self, topology, parent=None):
    self._create_identity()

    for cell in self.nodes:
        self._materialize(topology, cell, self.switch)  # backhaul 传给子单元

    if self.backhaul:
        if isinstance(self.backhaul, UpDownLink):
            uplink = Link(self.backhaul.bw_up, tags={'type': 'uplink', ...})
            downlink = Link(self.backhaul.bw_down, tags={'type': 'downlink', ...})

            # 上下行分离
            topology.add_connection(Connection(self.switch, uplink, latency_dist=...,
                                              ), directed=True)  # 内部走上行
            topology.add_connection(Connection(downlink, self.switch), directed=True)  # 外部进下行

            topology.add_connection(Connection(self.backhaul.backhaul, downlink, ...), directed=True)
            topology.add_connection(Connection(uplink, self.backhaul.backhaul), directed=True)

        else:
            topology.add_connection(Connection(self.switch, self.backhaul,
                                               latency_dist=latency.lan))
```

**两个细节**:

- `counters['lan']` 全局递增,保证 LANCell 名字唯一(`lan_0`、`lan_1`、...)
- `UpDownLink` 让上下行用**两条不同 Link + directed 边** —— 真实"非对称"场景

### 结构图

```
LANCell
├── Host_0 → switch_lan_0
├── Host_1 → switch_lan_0
└── switch_lan_0 → backhaul (or [up/down]link)
```

## 7. `SharedLinkCell` (268-326) —— 共享链路单元(**关键**)

### 与 LANCell 的区别

```
LANCell:       
[Host] → 
[Host] → switch
[Host] → 
SharedLinkCell:
[Host] →┐
[Host] →├→ shared_link
[Host] →┘
```

**所有 Host 共享同一条 Link**(默认 300 Mbit/s,模拟 WiFi AP、基站下行)。

### 字段

```python
def __init__(self, nodes, shared_bandwidth=300, backhaul=None):
    super().__init__(nodes=nodes, backhaul=backhaul)
    self.shared_bandwidth = shared_bandwidth
```

| 字段 | 含义 |
|---|---|
| `shared_bandwidth` | 共享接入链路总带宽(Mbit/s,默认 300) |

### `_create_identity` 和 `materialize`

```python
def _create_identity(self):
    self.nr = next(counters['shared'])
    self.name = 'shared_%d' % self.nr
    self.link = Link(bandwidth=self.shared_bandwidth,
                     tags={'name': self.name, 'type': 'shared'})

def materialize(self, topology, parent=None):
    self._create_identity()

    for cell in self.nodes:
        self._materialize(topology, cell, self.link)  # ← 共享 link 作为 backhaul

    if self.backhaul:
        if isinstance(self.backhaul, UpDownLink):
            # 与 LANCell 类似的 up/down 分离逻辑
            ...
        else:
            topology.add_connection(Connection(self.link, self.backhaul))
```

**关键设计**:`self._materialize(topology, cell, self.link)` —— 把 `self.link` 作为 backhaul 传给子单元,所以所有 Host 共享这条 Link。

## 8. `GeoCell` (329-372) —— 地理分布单元

### 字段

```python
def __init__(self, size, density, nodes):
    super().__init__(nodes, size)
    if isinstance(density, int):
        self.density = ConstantSampler(density)
    elif isinstance(density, RandomSampler):
        self.density = IntegerTruncationSampler(density)
    else:
        raise ValueError('unknown density type %s' % type(density))
```

| 字段 | 含义 |
|---|---|
| `size` | 生成多少个地理单元 |
| `density` | 每个单元内多少节点的采样器(int → `ConstantSampler`;`RandomSampler` → `IntegerTruncationSampler`) |

### `materialize`

```python
def materialize(self, topology, parent=None):
    for i in range(self.size):
        n = self.density.sample()    # 采样本单元节点数

        for c in self.nodes:
            if callable(c):
                sig: inspect.Signature = inspect.signature(c)
                if len(sig.parameters) > 0:
                    c = c(n)         # 工厂接收 density 采样值
                else:
                    c = c()
            self._materialize(topology, c)   # 递归展开
```

**两个 `size` 的关系**:

- `GeoCell.size` = "生成几个地理单元"(如 3 个城区)
- `density.sample()` = "每个城区生成多少节点"
- 两者独立配置

**注意**:`GeoCell` **不直接连 backhaul**,靠内部子单元(LANCell / SharedLinkCell)自己接。

### 设计要点

**工厂函数的 inspect**:

```python
sig = inspect.signature(c)
if len(sig.parameters) > 0:
    c = c(n)  # 工厂可以接收 density 采样值
else:
    c = c()   # 工厂无参
```

支持两种风格的工厂:

- 无参工厂:`def make_node(): return LANCell(...)`
- 带 density 工厂:`def make_node(n): return LANCell([...] * n, ...)`

## 9. 整体分层结构

```
UpDownLink  ← 上下行带宽/时延非对称回传配置
Cell        ← 基类(Composite + Factory)
Host        ← 1 Node + 1 Link
Client      ← Host 语法糖(用户)
Broker      ← Host 语法糖(MQTT 代理)
LANCell     ← N Host 共享一个 switch(透明顶点)
SharedLinkCell ← N Host 共享一条带宽受限 link
GeoCell     ← 按 size × density 重复生成子单元
```

**这个分层构成了 ether 怎么从"一个 Node"搭建出"一个城市边缘网络"**:

| 层次 | 角色 | 例子 |
|---|---|---|
| 资源层 | Node + Capacity | `Node('rpi3_0')` |
| 物理层 | Host(节点到链路的接入) | `Host(node, link_bw=1000)` |
| 网络层 | LANCell / SharedLinkCell(共享交换) | `LANCell([host1, host2, host3])` |
| 接入层 | UpDownLink(上下行非对称) | `UpDownLink(bw_down=1000, bw_up=100)` |
| 地理层 | GeoCell(城市级重复部署) | `GeoCell(size=10, density=...)` |

## 10. 对论文的接口清单

| 论文实验要素 | `cell.py` 提供的接口 | 关键位置 |
|---|---|---|
| 上下行非对称(移动/企业/光纤) | `UpDownLink(bw_down, bw_up, backhaul, latency_dist)` | 19-48 |
| 移动回传场景 | `UpDownLink` + `latency.mobile_isp` | `blocks/cells.py` 也有 `MobileConnection` |
| 单设备单元 | `Host(node, link_bw)` | 130-184 |
| 用户/客户端 | `Client(name)` | 186-196 |
| MQTT 代理 | `Broker(name)` | 198-207 |
| 局域网单元(共享交换机) | `LANCell(nodes, backhaul)` | 210-266 |
| 共享带宽链路(WiFi AP / 基站) | `SharedLinkCell(nodes, shared_bandwidth)` | 268-326 |
| 城市级重复部署 | `GeoCell(size, density, nodes)` | 329-372 |
| 真实节点数分布 | `density = ParameterizedDistribution.lognorm(...)` | 329-372 + `srds` |
| 工厂模式 | `Cell._materialize` 处理 Node/Cell/Callable/Iterable | 102-127 |
| 物化入口 | `Cell.generate() -> Topology` | 91-100 |

### 典型场景拼装

```python
# 一个工厂:3 个 RPI3 共享 WiFi,企业 ISP 上联
factory_iot = SharedLinkCell(
    nodes=[nodes.rpi3] * 3,         # 3 个工厂函数,每次调用生成一个 RPI3
    shared_bandwidth=500,            # 500 Mbit/s 共享
    backhaul=BusinessIsp('internet') # 企业 ISP
)

# 一个城市:5 个城区,每个城区节点数从对数正态采样
city = GeoCell(
    size=5,
    density=ParameterizedDistribution.lognorm((0.82, 2.02)),
    nodes=[neighborhood_factory]
)
```
