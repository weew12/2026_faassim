# faas-sim 中的 Skippy 适配层

Skippy 自己只理解 `Node`、`Pod`、`ImageState`、`StorageIndex` 等对象。但 faas-sim 的世界里有 Ether 节点、函数部署、容器仓库、拓扑和资源状态。

`sim/skippy.py` 的职责就是做转换。

## `SimulationClusterContext`

`SimulationClusterContext` 继承自：

```python
skippy.core.clustercontext.ClusterContext
```

它把 faas-sim 的环境暴露给 Skippy。

重要字段：

- `env`
- `topology`
- `container_registry`
- `bw_graph`
- `nodes`
- `storage_index`
- `_storage_nodes`

## 节点转换：Ether Node -> Skippy Node

转换函数：

```python
to_skippy_node(node: EtherNode) -> SkippyNode
```

转换内容：

- Ether 节点名 -> Skippy 节点名；
- Ether capacity -> Skippy capacity；
- capacity 拷贝一份作为 allocatable；
- Ether labels -> Skippy labels；
- 额外写入 `beta.kubernetes.io/arch`。

代码核心：

```python
capacity = SkippyCapacity(node.capacity.cpu_millis, node.capacity.memory)
allocatable = copy.copy(capacity)
labels = dict(node.labels)
labels["beta.kubernetes.io/arch"] = node.arch
```

## 函数转换：FunctionDeployment -> Pod

转换函数：

```python
create_function_pod(fd, fn) -> Pod
```

输入：

- `fd`：FunctionDeployment；
- `fn`：FunctionContainer。

输出：

- Skippy Pod。

转换内容：

```text
FunctionContainer.image -> Container.image
FunctionContainer.resource_config -> ResourceRequirements
FunctionContainer.labels -> PodSpec.labels
FunctionDeployment.name -> Pod name 前缀
```

## 镜像状态：ContainerRegistry -> ImageState

`retrieve_image_state(image_name)` 从 faas-sim 容器仓库读取镜像元数据。

如果镜像未声明架构，适配层会把同一大小复制到常见架构：

- `x86`
- `arm`
- `arm32v7`
- `aarch64`
- `arm64`
- `amd64`

如果镜像声明了架构，则构造成：

```python
{
    image.arch: image.size
}
```

这让 Skippy 可以按目标节点架构判断镜像大小。

## 带宽图：Topology -> LazyBandwidthGraph

Skippy 需要：

```python
bandwidth[from_node][to_node]
```

faas-sim 的真实网络信息在 Ether Topology 中。适配层用：

```python
LazyBandwidthGraph(self.topology)
```

把拓扑转换成延迟查询带宽图。

好处：

- 不提前构造完整矩阵；
- 只在优先级函数真正访问某条链路时计算；
- 可以缓存已经查询过的结果。

## 存储节点

`storage_nodes` 属性会筛选带有：

```text
data.skippy.io/storage
```

标签的节点。

`get_next_storage_node(node)` 会选择离节点最近的存储节点，当前按带宽最大原则选择。

## 与 DefaultFaasSystem 的连接

默认仿真装配中：

```python
env.cluster = SimulationClusterContext(env)
env.scheduler = Scheduler(env.cluster)
```

当 `DefaultFaasSystem.run_scheduler_worker()` 从 `scheduler_queue` 取出副本后，会执行：

```python
result = env.scheduler.schedule(pod)
```

如果 `result.suggested_host` 存在：

```python
replica.node = env.get_node_state(result.suggested_host.name)
env.process(simulate_function_start(env, replica))
```

这就是 Skippy 调度结果进入 faas-sim 生命周期模拟的关键连接点。

