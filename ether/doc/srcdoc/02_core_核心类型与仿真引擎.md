# 02 · core 核心类型与仿真引擎

> 本文档解析 `ether/core.py`(537 行,最重的文件),这是 ether 整个仿真系统的基础。
>
> **核心内容**:Node/Capacity/Link/Connection/Route/Flow 五大基础类型 + 公平共享带宽算法 + SimPy 协程驱动的 Flow 传输

## 1. 文件概览

| 项 | 值 |
|---|---|
| 行数 | 537 |
| 导入 | `abc`、`logging`、`typing`、`numpy`、`simpy`、`srds.ParameterizedDistribution` |
| 核心类 | `Connection`、`Capacity`、`Coordinate`、`Node`、`Route`、`Flow`、`UninterruptingFlow`、`Link` |
| 全局函数 | `add_and_rebalance`、`remove_and_rebalance`、`rebalance`、`add_without_rebalance`、`remove_without_rebalance`、`collect_subnet` |
| 角色 | **Layer 1** —— ether 整个仿真引擎的基础 |

## 2. 顶层类型别名(13-19 行)

```python
TransparentLink = AnyStr
"""透明链路表示交换机、路由器、互联网骨干等辅助顶点;
它们参与路由连通性,但不直接作为计算节点。"""

NetworkNode = Union['Node', 'Link', TransparentLink]
"""网络顶点可以是计算节点、链路对象或透明链路标识,
是 Ether 拓扑图中的统一顶点类型。"""
```

| 类型别名 | 等价于 | 含义 |
|---|---|---|
| `TransparentLink` | `str` | 交换机、路由器、骨干网等"只转发不计算"的辅助顶点(用字符串表示) |
| `NetworkNode` | `Union[Node, Link, str]` | ether 拓扑图里**统一的顶点类型** |

**意义**:后续图遍历、路由计算时,要把"字符串 ID"和"对象"一视同仁地当作顶点处理。

## 3. `Connection` (22-68) —— 拓扑边

```python
class Connection(NamedTuple):
    source: NetworkNode
    target: NetworkNode
    latency: float = 0
    latency_dist: ParameterizedDistribution = None
```

四个字段:

| 字段 | 含义 |
|---|---|
| `source` | 源顶点(Node/Link/TransparentLink) |
| `target` | 目标顶点 |
| `latency` | **固定**单向链路时延(毫秒) |
| `latency_dist` | **随机分布**链路时延(`srds.ParameterizedDistribution`) |

### 三个查询方法

| 方法 | 行为 |
|---|---|
| `get_latency()` | **本次使用**的单向时延,有分布则采样,否则返回固定值 |
| `get_mode_latency()` | **众数近似**(假设对数正态 `exp(log(scale) - sigma²) + loc`),用于**路由缓存阶段**生成稳定基准 RTT |
| `get_mean_latency()` | 分布的**平均值**,统计分析用 |

### 设计要点

- `latency` 和 `latency_dist` **二选一**:`get_latency()` 优先用分布
- 众数近似假设对数正态分布(适配内置的 `qos.latency` 4 个分布)
- 后续可扩展更细粒度的 QoS 模型(丢包、抖动、协议差异)

## 4. `Capacity` (71-92) —— 节点资源

```python
class Capacity:
    def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1024 * 1024 * 1024):
        self.memory = memory
        self.cpu_millis = cpu_millis
```

| 字段 | 单位 | 默认值 |
|---|---|---|
| `cpu_millis` | 毫核(millicores) | 1000 = 1 核 |
| `memory` | 字节 | 1 GB |

**对论文**:用 **millicores** 不用"核数",精度更高,符合 Kubernetes 资源模型。

## 5. `Coordinate` (95-107) —— 抽象坐标

```python
class Coordinate(abc.ABC):
    def distance_to(self, other: 'Coordinate') -> float:
        pass
```

纯抽象接口,只要求 `distance_to`。**`VivaldiCoordinate`(`vivaldi.py`)实现这个接口** —— 把节点映射到虚拟欧几里得空间,用欧式距离估算 RTT。

## 6. `Node` (110-174) —— 节点本体

### 字段

| 字段 | 含义 |
|---|---|
| `name` | 业务/拓扑标识 |
| `capacity` | `Capacity` 实例 |
| `arch` | CPU 架构(`x86`/`arm32`/`aarch64`),用于匹配容器镜像 |
| `labels` | 标签字典(K8s 风格) |
| `coordinate` | 可选坐标(`None` 默认,要测量/估算时再设) |

### 关键方法

**`__hash__ = hash(self.name)`** —— **按名字身份参与图**,意味着可以用 `name` 字符串和 `Node` 对象互换作为 dict / graph 顶点。

**`distance_to(other)`** —— 委托给 `self.coordinate.distance_to(other.coordinate)`,坐标未设置时硬性 `AssertionError`。

### 设计要点

- `coordinate = None` 默认(惰性初始化)
- 节点自己不实现坐标,**委托**给 Coordinate 子类
- 两个 `AssertionError`:坐标未设置不允许参与距离计算

## 7. `Route` (177-224) —— 端到端路由

### 字段

| 字段 | 含义 |
|---|---|
| `source` / `destination` | Node 端点 |
| `path` | 最短路径解出的**完整顶点序列**(含透明链路、Link、Node) |
| `hops` | **过滤后**的 Link 列表 —— `path` 里 `isinstance(hop, Link)` 筛出 |
| `rtt` | 往返时延(**双向**!) |

### 关键方法

**`__init__` 里的关键一行 (208)**:

```python
self.hops = [hop for hop in path if isinstance(hop, Link)]
```

这是后面"带宽分配"的接口 —— 流量只会消耗 `hops` 里真实 Link 的带宽,不会算到透明交换机上。

**`__copy__`** —— 返回新 Route 对象,**避免随机时延采样污染共享缓存**。调用方拿到的 `route.rtt` 如果是采样得到的,需要自己 copy 再用,否则会随每次访问变化。

## 8. `Flow` (227-360) —— 网络流(SimPy 协程)

### 字段

| 字段 | 含义 |
|---|---|
| `env` | SimPy 仿真环境 |
| `size` | 总字节数 |
| `route` | 已经规划好的路由 |
| `sent` | 已传字节数 |
| `process` | SimPy 进程对象 |

### `get_goodput_bps()` (270-277)

```python
return min([link.get_goodput_bps(self) for link in self.route.hops])
```

端到端 goodput = **所有链路分配的瓶颈**。水桶效应,经典。

### `run()` (279-341) —— 4 阶段传输协程

```
[1] TCP 握手  = 1.5 * RTT / 1000  (env.timeout 推进)
[2] add_and_rebalance(self)       ← 新流登入链路,触发全局带宽重分
[3] while True:
      env.timeout(transmission_time)  ← SimPy 推进
      ↑ 若被 Interrupt(其他流退出/加入)打断
        → 重算 sent / bytes_remaining / goodput / transmission_time
        → 再 yield 一次新 timeout
[4] finally: remove_and_rebalance(self)  ← 释放链路占用
```

### `establish()` (343-360)

只模拟建连,不做数据传输,也是 RTT 驱动的超时循环。

### 关键设计

- **`simpy.Interrupt` 中断驱动重算**:任何流的加入/离开都会通过 rebalance 触发其他活动流的 `Interrupt.cause` 改变
- 被中断的流重新评估 `bytes_remaining / goodput`,继续等待
- **离散事件仿真里公平共享带宽的经典实现**

## 9. `Link` (362-460) —— 链路对象

### 字段

| 字段 | 含义 |
|---|---|
| `bandwidth` | 标称带宽,单位 **Mbit/s** |
| `tags` | 链路标签字典 |
| `allocation` | `Dict[Flow, float]` —— 每流当前分配(Mbit/s),由 rebalance 维护 |
| `num_flows` | 当前活跃流数量 |
| `max_allocatable` | 公平分配后单流上限(Mbit/s) |

### `recalculate_max_allocatable()` (398-424) —— 公平份额算法

```python
num_flows = self.num_flows
bandwidth = self.bandwidth

if num_flows == 0:
    self.max_allocatable = bandwidth
    return

fair_per_flow = bandwidth / num_flows
reserved = {k: v for k, v in self.allocation.items() if v < fair_per_flow}  # 小流保留
allocatable = bandwidth - sum(reserved.values())

competing_flows = num_flows - len(reserved)
if competing_flows:
    allocatable_per_flow = allocatable / competing_flows
else:
    allocatable_per_flow = allocatable

self.max_allocatable = max(fair_per_flow, allocatable_per_flow)
```

**核心思想**:

- `fair_per_flow = bandwidth / num_flows`(理想等分)
- 已经分配 < fair 的流**保留原分配**(避免无意义抢占)
- 剩余流竞争剩余带宽
- `max_allocatable = max(fair_per_flow, allocatable/competing)`

### `get_goodput_bps(flow)` (426-446)

```python
if flow not in self.allocation:
    return None
allocated = self.allocation[flow]
practical_bw = allocated * 125000       # Mbit/s → B/s
goodput_magic_number = 0.97              # rough estimate of goodput (~ TCP overhead)
return practical_bw * goodput_magic_number
```

注释里说得很直白:
> 当前 goodput 模型保留为轻量近似,便于大规模仿真。
> 可在此引入 TCP 多流退化函数,进一步模拟大量并发流带来的协议开销。

**关键提示**:这里留了**扩展点** —— 论文里如果要做更细粒度的网络效应,可以扩展这里。

## 10. 三个 rebalance 函数(463-549) —— 调度核心

| 函数 | 行号 | 作用 |
|---|---|---|
| `add_and_rebalance(flow)` | 483-498 | 新流登入,触发重分 |
| `remove_and_rebalance(flow)` | 463-480 | 旧流离开,触发重分 + 释放 `allocation[flow]` |
| `rebalance(triggering_flow, affected, links)` | 501-549 | **max-min fairness** 分配 |
| `add_without_rebalance(flow)` | 566-580 | 非抢占:按当前瓶颈一次分配,不触全局重分 |
| `remove_without_rebalance(flow)` | 552-565 | 非抢占:不打断其他流 |

### `rebalance` 核心循环 (501-549)

```python
allocation: Dict[Flow, float] = dict()

while affected_flows:
    # 1. 算每个流在所有路径上的瓶颈
    bottlenecks = {flow: min([link.max_allocatable for link in flow.route.hops]) for flow in affected_flows}
    
    # 2. 找瓶颈最小的流
    flow = min(bottlenecks, key=lambda k: bottlenecks[k])
    request = bottlenecks[flow]
    
    # 3. 给它分配瓶颈值,更新每条链路的 max_allocatable
    changed = False
    for link in flow.route.hops:
        if link.allocation.get(flow) == request:
            continue
        changed = True
        link.allocation[flow] = request
        link.recalculate_max_allocatable()
    
    if changed:
        allocation[flow] = request
    
    # 4. 剔除已处理流
    del bottlenecks[flow]
    affected_flows.remove(flow)

# 5. 给所有受影响的流(除触发者)发 Interrupt
for flow, bw in allocation.items():
    if flow is triggering_flow:
        continue
    if not flow.process.is_alive:
        continue
    flow.process.interrupt(bw)   # ← 关键!打断 SimPy 协程
```

**这是教科书级 max-min fairness 实现**:

1. 反复找"瓶颈最小的流"
2. 给它瓶颈值
3. 让所有链路重算剩余可用带宽
4. 处理下一个流
5. 完成后用 `process.interrupt(bw)` **主动打断**受影响的 SimPy 协程
6. 让它们在 `Flow.run()` 的 `except simpy.Interrupt` 分支里重算剩余传输时间

## 11. `UninterruptingFlow` (582-652) —— 背景流量变体

```python
class UninterruptingFlow(Flow):
    def run(self):
        # 几乎与 Flow.run() 一模一样
        # 区别:用 add_without_rebalance / remove_without_rebalance
        ...
```

跟 `Flow` 几乎一样,只是 `add/rebalance` 换成 `add/remove_without_rebalance` —— **不打断已存在的流**。代码直接复制粘贴 `Flow.run()` 改的,**潜在重构点**。

**用途**:模拟"已知会一直存在的低优先级背景流量",不该每次拉镜像都重新打断别人。

## 12. `collect_subnet` (655-692) —— BFS flood fill 找"受影响子集"

```python
def collect_subnet(flow: Flow):
    affected_links = set()
    affected_flows = set()
    stack = set()
    stack.add(flow)

    while stack:
        elem = stack.pop()
        if isinstance(elem, Link):
            if elem in affected_links:
                continue
            affected_links.add(elem)
            flows = elem.allocation.keys()
            stack.update(flows)

        elif isinstance(elem, Flow):
            if elem in affected_flows:
                continue
            affected_flows.add(elem)
            links = elem.route.hops
            stack.update(links)
        else:
            raise ValueError('element of type %s not handled: %s' % (type(elem), elem))

    return affected_flows, affected_links
```

**Link ↔ Flow 双向 BFS**:从触发流出发,沿着"流→链路→共享该链路的流→这些流的链路→..."找出所有"在网络流图上联通"的元素。

**意义**:rebalance 只处理**真正受影响的子集**,避免每次都对全网所有流重算。

- O(受影响子集),不是 O(所有流)
- 典型场景下小得多 → 大规模仿真能 scale

## 13. 整体四层抽象总结

```
1. Capacity / Node / Coordinate          ← 资源层(节点有什么)
2. Connection (NamedTuple) / Link        ← 拓扑层(节点怎么连)
3. Route (含 hops / rtt)                 ← 路由层(走哪条路)
4. Flow + UninterruptingFlow             ← 传输层(SimPy 协程 + 公平共享 + 中断驱动)
```

**+ 三个全局函数**:`add_and_rebalance` / `remove_and_rebalance` / `rebalance` —— 仿真引擎的"调度器"。

## 14. 对论文的完整接口清单

| 论文实验要素 | `core.py` 提供的接口 | 关键位置 |
|---|---|---|
| 节点 CPU/内存 | `Node.capacity: Capacity` | `__init__` 123-143 |
| 节点架构 | `Node.arch: str` | 117 |
| 节点标签(能力) | `Node.labels: Dict[str, str]` | 119 |
| 镜像架构约束调度 | `if node.arch != image.arch: skip` | 用户代码 |
| GPU/TPU 调度 | `if 'cuda' in node.labels[...]` | 用户代码 |
| 节点坐标/距离 | `Node.distance_to(other)` | 152-167 |
| 边时延模型 | `Connection.latency / latency_dist` | 22-44 |
| 稳定基准 RTT | `Connection.get_mode_latency()` | 46-57 |
| 单次采样 RTT | `Connection.get_latency()` | 35-44 |
| 端到端路由 | `Route.hops`、`Route.rtt` | 177-217 |
| 路由拷贝(防污染) | `Route.__copy__` | 219-224 |
| 单次数据传输 | `Flow(env, size, route)` + `start()` | 227-268 |
| 端到端瓶颈带宽 | `Flow.get_goodput_bps()` | 270-277 |
| 仿真耗时 | `Flow.run()` 完成时间 | 279-341 |
| 流传输进度 | `Flow.sent` | 230, 256 |
| 公平共享带宽 | `Link.allocation`、`recalculate_max_allocatable` | 371-424 |
| 链路 goodput | `Link.get_goodput_bps(flow)` | 426-446 |
| 流加入/离开 | `add_and_rebalance` / `remove_and_rebalance` | 463-498 |
| 带宽重分配算法 | `rebalance` | 501-549 |
| 背景流量 | `UninterruptingFlow` | 582-652 |
| 受影响流 BFS | `collect_subnet` | 655-692 |
