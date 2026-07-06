# 04 · topology DiGraph 与路由缓存

> 本文档解析 `ether/topology.py`(196 行,2 个类),这是 ether 的"图与路由层"—— 把 `core.py` 的 `Connection/Node/Link` 装进 `networkx.DiGraph`,加上路由缓存和 RTT 计算。
>
> **核心内容**:`Topology(nx.DiGraph)` 子类,提供 add_connection、route 缓存、两种 RTT 模式(load_inet_graph 入口)

## 1. 文件概览

| 项 | 值 |
|---|---|
| 行数 | 196 |
| 导入 | `abc`、`logging`、`copy`、`typing`、`networkx`、`ether.core.{Node, Link, Connection, Route, NetworkNode}`、`ether.inet.graph.load_latest` |
| 类数 | 2(`Template` 抽象 + `Topology`) |
| 角色 | **Layer 3** —— 在 core.py 之上提供"图查询"和"路由计算"接口 |

## 2. `Template` (16-26) —— 可物化拓扑模板抽象

```python
class Template(abc.ABC):
    def materialize(self, topology: 'Topology'):
        ...
```

**纯接口约束**,只有 `materialize` 抽象方法。`Topology.add(cell)` 会调这个方法,需要 cell 是 Template 子类。

实际上这个抽象在 ether 里用得不多 —— `Topology` 接收任何有 `materialize(topology)` 方法的对象,不强依赖 `Template` 抽象。

## 3. `Topology(nx.DiGraph)` (29-196) —— Ether 拓扑图

### 字段

```python
class Topology(nx.DiGraph):
    def __init__(self, incoming_graph_data=None, **attr):
        super().__init__(incoming_graph_data, **attr)
        # 源节点到目标节点的路由缓存,避免重复执行最短路径计算
        self._route_cache: Dict[Tuple[NetworkNode, NetworkNode], Route] = dict()
```

| 字段 | 含义 |
|---|---|
| (继承自 nx.DiGraph) | 标准有向图所有字段 |
| `_route_cache` | `Dict[(source, dest), Route]` —— **路由缓存** |

### `conn(...)` —— `add_connection` 的简写

```python
def conn(self, *args, **kwargs):
    return self.add_connection(*args, **kwargs)
```

### `add_connection(connection, directed=False)` (47-60)

```python
def add_connection(self, connection: Connection, directed=False):
    if isinstance(connection.source, Node) and isinstance(connection.target, Node):
        raise ValueError('Cannot have direct Node-to-Node connections')

    self.add_edge(connection.source, connection.target, directed=directed, connection=connection)
    if directed is False:
        self.add_edge(connection.target, connection.source, directed=directed, connection=connection)
```

**两个关键点**:

1. **强制不变量**:`Node → Node` 直连 → `ValueError`。这是 ether 拓扑的**硬约束**:Node 永远是"叶子",必须经过 Link 或 TransparentLink
2. **无向连接自动加反向边**:`directed=False` 时,正向/反向各加一条 edge

### `path(source, destination)` (62-73)

```python
def path(self, source, destination):
    return nx.shortest_path(self, source, destination)
```

直接调 `networkx.shortest_path`,**不缓存**(每次重算)。

### `latency(source, destination, use_coordinates=False)` (75-89) —— 单向时延

```python
def latency(self, source: Node, destination: Node, use_coordinates=False) -> float:
    if use_coordinates:
        return source.distance_to(destination)   # 走 Vivaldi/地理坐标
    return self.route(source, destination).rtt / 2   # 走拓扑路由(RTT/2)
```

**两种 RTT 模式**:

| `use_coordinates` | 模式 | 性能 | 精确度 |
|---|---|---|---|
| `False`(默认) | 拓扑模式:shortest_path + 累加 Connection.latency | O(E) | **精确**,需要建好拓扑 |
| `True` | 坐标模式:Vivaldi 坐标距离 | O(d) | 轻量估算 |

### `route(source, destination, use_mode=False)` (91-116) —— **关键:路由缓存**

```python
def route(self, source, destination, use_mode: bool = False) -> Route:
    k = (source, destination)

    if k not in self._route_cache:
        # 首次查询时解析最短路径并写入缓存,降低重复路由计算开销
        self._route_cache[k] = self._resolve_route(source, destination)

    if not use_mode:
        route = copy(self._route_cache[k])   # ← 拷贝,防污染
        self._update_rtt(route)              # ← 重新采样随机 RTT
    else:
        route = self._route_cache[k]         # ← 用众数,稳定

    return route
```

**设计精妙**:

- 缓存用**众数 RTT**(稳定基准),用 `copy()` 防止污染
- 实际使用时**重新采样** RTT(体现网络抖动)
- `use_mode=True` 时直接返回缓存(用众数,适合调度决策时)

**这就是为什么 `core.py` 的 `Connection` 既有 `get_latency()` 又有 `get_mode_latency()`** —— 一个给"使用",一个给"缓存"。

### `get_nodes()` / `get_links()` (118-134)

```python
def get_nodes(self):
    return [n for n in self.nodes if isinstance(n, Node)]

def get_links(self):
    return [n for n in self.nodes if isinstance(n, Link)]
```

按类型过滤 `topology.nodes`。`switches`(字符串形式的透明链路)不被这两个方法返回,但仍然是图顶点。

### `load_inet_graph(source)` (136-144)

```python
def load_inet_graph(self, source):
    load_latest(self, source)
```

加载预置互联网区域延迟图(在 `inet/` 子包),支持 `cloudping` / `gcloudping` / `wondernetwork` 三种数据源。

**调用链**:`Topology.load_inet_graph('cloudping')` → `inet.graph.load_latest(self, 'cloudping')` → 读 `cloudping_latest.graphml` → 加 `internet_` 前缀 → 写入图。

### `_resolve_route(source, destination)` (146-160)

```python
def _resolve_route(self, source, destination) -> Route:
    path = self.path(source, destination)
    route = Route(source, destination, path=path)
    self._update_rtt(route, use_mode=True)   # ← 用众数写缓存
    return route
```

### `_update_rtt(route, use_mode=False)` (162-183) —— 沿路径累加时延

```python
def _update_rtt(self, route: Route, use_mode: bool = False):
    latency: float = 0
    for i in range(len(route.path)-1):
        edge_data = self.get_edge_data(route.path[i], route.path[i + 1])
        if 'connection' in edge_data and isinstance(edge_data['connection'], Connection):
            connection: Connection = edge_data['connection']
            latency += connection.get_mode_latency() if use_mode else connection.get_latency()
        elif 'latency' in edge_data:
            # 互联网 graphml 数据中的边通常直接保存固定 latency 属性
            latency += edge_data['latency']
    route.rtt = latency * 2   # ← RTT = 双向
```

**双源支持**:

- ether 自己的边 → `edge_data['connection']` 是 `Connection` 对象 → 走 `get_mode_latency()` / `get_latency()`
- internet graphml 数据 → `edge_data['latency']` 是数值 → 直接加

**注意**:`route.rtt` 是**双向**(RTT),所以最后 `× 2`。

### `add(cell)` (185-196) —— 物化入口,链式调用

```python
def add(self, cell):
    cell.materialize(self)
    return self
```

**支持链式风格**:`topology.add(lan_cell).add(geo_cell).add(internet_graph)`。

## 4. 关键设计要点

### 1) 强制拓扑不变量

`add_connection` 强制:`Node → Node` 不能直连,必须经过 Link 或 TransparentLink。这跟 `core.py` 的 `NetworkNode = Union[Node, Link, TransparentLink]` 是配套的。

### 2) 路由缓存的双时延模式

| 模式 | 何时用 | 性能 |
|---|---|---|
| `use_mode=True` | 缓存写入、调度决策、统计分析 | 快,直接返回缓存 |
| `use_mode=False` | 实际仿真时使用 | 稍慢,需要重算 RTT |

### 3) 双源 RTT 数据

`Connection`(ether 生成) 和 `latency` 字段(graphml 数据) 都能被 `_update_rtt` 处理。

### 4) 两套 RTT 查询模式

| 模式 | 接口 | 用途 |
|---|---|---|
| 拓扑模式 | `latency(src, dst)` → `route.rtt / 2` | 精确,适合"决策要用真实路径" |
| 坐标模式 | `latency(src, dst, use_coordinates=True)` → `src.distance_to(dst)` | 轻量,适合"节点很多时估算" |

## 5. 对论文的接口清单

| 论文实验要素 | `topology.py` 提供的接口 | 关键位置 |
|---|---|---|
| 节点间 RTT(精确) | `Topology.route(src, dst)`、`Topology.latency(src, dst)` | 75-116 |
| 节点间 RTT(轻量) | `Topology.latency(src, dst, use_coordinates=True)` | 75-89 |
| 最短路径 | `Topology.path(src, dst)` | 62-73 |
| 加载云区域延迟 | `Topology.load_inet_graph('cloudping')` | 136-144 |
| 添加 Cell(链式) | `topology.add(cell).add(cell2)` | 185-196 |
| 强制拓扑约束 | `Cannot have direct Node-to-Node connections` | 55-56 |
| 路由缓存(防污染) | `_route_cache` + `copy()` | 38, 110 |
| 缓存使用模式 | `route(src, dst, use_mode=True)` | 91-116 |
| 按类型过滤节点 | `get_nodes()` / `get_links()` | 118-134 |
| 双源 RTT(Connection / latency 字段) | `_update_rtt` | 162-183 |

### 典型用法

```python
from ether.topology import Topology
from ether.scenarios import UrbanSensingScenario

t = Topology()
t.add(UrbanSensingScenario())   # 链式: 物化场景
t.load_inet_graph('cloudping')  # 加载真实云区域延迟

# 节点间 RTT
rtt = t.route(node_a, node_b).rtt         # 精确(采样)
rtt_mode = t.route(node_a, node_b, use_mode=True).rtt  # 稳定(众数)
one_way = t.latency(node_a, node_b)        # RTT / 2

# 轻量 RTT
quick = t.latency(node_a, node_b, use_coordinates=True)  # Vivaldi 距离
```
