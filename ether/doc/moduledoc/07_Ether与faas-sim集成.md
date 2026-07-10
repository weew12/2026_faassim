# Ether 与 faas-sim 集成

## 1. 集成关系总览

faas-sim 使用 Ether 做网络与拓扑层。

主要集成点：

| faas-sim 位置 | Ether 能力 |
|---|---|
| `sim/topology.py` | 包装 Ether Topology，增加 registry 节点和按节点名路由 |
| `sim/net.py` | 基于 Ether Flow 增加低带宽检查 |
| `sim/docker.py` | 用 Ether Flow 模拟镜像拉取 |
| `sim/faas/system.py` | 用 Ether 拓扑模拟数据下载/上传 |
| `sim/skippy.py` | 把 Ether Node 转换成 Skippy Node |
| `ext/raith21/*` | 用 Ether 构造实验拓扑和设备 |

## 2. sim.topology.Topology

faas-sim 自己定义了一个 `sim.topology.Topology`，它继承自 Ether 的 `ether.topology.Topology`。

增强能力：

- 初始化 Docker registry 节点。
- 按节点名查找 Ether Node。
- 按节点名查询路由。
- 延迟构造带宽图。

典型用途：

```python
route = env.topology.route_by_node_name("node-a", "node-b")
```

## 3. sim.net.SafeFlow

Ether 的 `Flow` 会模拟传输时间，但如果路由不可用或带宽极低，业务层可能希望提前报错。

`sim.net.SafeFlow` 在 Ether Flow 外层加了一层检查：

- 如果链路不可用，抛异常。
- 如果带宽低于阈值，抛异常。
- 正常情况下返回 Ether Flow。

这能避免实验静默跑出不合理结果。

## 4. Docker 镜像拉取

`sim/docker.py` 中的 `pull()` 会：

1. 根据镜像名和节点架构从容器仓库查找镜像。
2. 检查目标节点是否已有镜像缓存。
3. 如果没有缓存，计算 registry 到目标节点的路由。
4. 创建 `SafeFlow`。
5. 通过 Ether Flow 模拟镜像传输耗时。
6. 记录 flow 指标。

对应业务含义：

```text
函数副本部署到节点前，需要先把容器镜像拉到节点。
镜像越大、链路越慢，启动越慢。
```

## 5. 数据下载与上传

`sim/faas/system.py` 中有：

- `simulate_data_download()`
- `simulate_data_upload()`

它们会读取 Pod label：

- `data.skippy.io/receives-from-storage`
- `data.skippy.io/receives-from-storage/path`
- `data.skippy.io/sends-to-storage`
- `data.skippy.io/sends-to-storage/path`

然后：

1. 找到数据所在存储节点。
2. 查询副本节点与存储节点之间的 Ether route。
3. 创建 `SafeFlow`。
4. 记录链路级 network 指标和端到端 flow 指标。

注意：默认 `simulate_function_invocation()` 不自动调用下载/上传。具体模拟器需要显式调用这些函数。

## 6. Skippy 调度适配

`sim/skippy.py` 把 Ether 节点转换为 Skippy 节点：

```python
def to_skippy_node(node: EtherNode) -> SkippyNode:
    capacity = SkippyCapacity(node.capacity.cpu_millis, node.capacity.memory)
    allocatable = copy.copy(capacity)
    labels = dict(node.labels)
    labels["beta.kubernetes.io/arch"] = node.arch
    return SkippyNode(node.name, capacity=capacity, allocatable=allocatable, labels=labels)
```

转换重点：

- Ether 的 `Capacity` 转成 Skippy 的 `Capacity`。
- Ether 的 `labels` 保留给调度器使用。
- Ether 的 `arch` 写入 Kubernetes 风格架构标签。

这样 Skippy 可以用 Ether 节点做调度决策。

## 7. 调度后如何回到 Ether

调度器返回的是 Skippy 节点：

```python
result.suggested_host
```

faas-sim 会用节点名回到 Ether/faas-sim 节点状态：

```python
replica.node = env.get_node_state(result.suggested_host.name)
```

`NodeState` 中同时保存：

- `ether_node`
- `skippy_node`

这样同一个节点可以同时参与：

- Ether 网络传输。
- Skippy 调度。
- faas-sim 资源和请求状态记录。

## 8. 一个完整函数部署链路

```text
Benchmark.run()
  |
  v
env.faas.deploy(function_deployment)
  |
  v
DefaultFaasSystem.scale_up()
  |
  v
deploy_replica()
  |
  v
scheduler_queue.put(replica)
  |
  v
run_scheduler_worker()
  |
  v
Skippy Scheduler 选择节点
  |
  v
env.get_node_state(节点名)
  |
  v
simulate_function_start()
  |
  v
simulator.deploy()
  |
  v
docker.pull() / Ether Flow 镜像传输
  |
  v
replica.state = RUNNING
```

Ether 主要在“拓扑查询”和“镜像传输”阶段发挥作用。

## 9. 一个完整请求调用链路

```text
function_trigger()
  |
  v
env.faas.invoke(FunctionRequest)
  |
  v
负载均衡选择 RUNNING 副本
  |
  v
simulate_function_invocation()
  |
  v
replica.simulator.invoke()
  |
  +-- 可选：simulate_data_download() -> Ether Flow
  +-- 可选：函数执行耗时
  +-- 可选：simulate_data_upload() -> Ether Flow
```

Ether 是否参与请求调用，取决于具体 simulator 是否显式调用数据下载/上传函数。

## 10. 使用 Ether 建 faas-sim 拓扑的建议

### 小实验

使用 `ether.core` 手工创建 4 个 server 节点即可。

优点：

- 节点稳定。
- 容易控制资源和链路。
- 适合调试调度器、伸缩器、缓存策略。

### 网络流实验

手工创建 bottleneck 链路。

优点：

- 能清楚观察多流共享带宽。
- 适合验证 Ether Flow 行为。

### 大场景实验

使用 `ether.scenarios`。

优点：

- 快速生成城市、工业、云区域场景。
- 更接近论文实验。

注意：

部分场景使用全局计数器或随机分布，连续构造时节点名可能变化。需要做对比实验时，建议复用同一份 topology，或手工构造稳定拓扑。

## 11. 最常见调试方法

检查节点：

```python
for node in topology.get_nodes():
    print(node.name, node.arch, node.capacity, node.labels)
```

检查路由：

```python
route = topology.route_by_node_name("a", "b")
print(route.path)
print(route.hops)
print(route.rtt)
```

检查链路：

```python
for link in topology.get_links():
    print(link.tags, link.bandwidth)
```

检查 faas-sim 中的节点状态：

```python
state = env.get_node_state("node-name")
print(state.ether_node)
print(state.skippy_node)
print(state.docker_images)
```
