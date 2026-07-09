# 核心对象模型：Node、Pod、Container

Skippy 的调度对象模仿 Kubernetes，但只保留仿真调度需要的字段。

## 总览

```text
Pod
  └─ PodSpec
       ├─ containers: List[Container]
       └─ labels: Dict[str, str]

Container
  ├─ image: str
  └─ resources: ResourceRequirements

Node
  ├─ name: str
  ├─ capacity: Capacity
  ├─ allocatable: Capacity
  ├─ labels: Dict[str, str]
  └─ pods: List[Pod]
```

## `ImageState`

`ImageState` 表示调度器视角下的镜像元数据。

字段：

- `size`：不同 CPU 架构下的镜像大小；
- `num_nodes`：当前已经缓存该镜像的节点数量。

示例：

```python
ImageState({
    "amd64": 500_000_000,
    "arm64": 420_000_000,
})
```

调度器使用它判断：

- 某个节点缺失镜像时需要拉多少数据；
- 镜像本地性得分如何计算；
- `SchedulingResult.needed_images` 应该包含哪些镜像。

## `ResourceRequirements`

`ResourceRequirements` 表示容器资源请求。

默认值：

```python
default_requests = {
    "cpu": 100,
    "memory": 200 * 1024 * 1024,
}
```

CPU 单位是 millicore。`1000` 表示 1 个 CPU 核。

资源谓词会读取：

```python
container.resources.requests["cpu"]
container.resources.requests["memory"]
```

然后和节点剩余资源比较。

## `Container`

`Container` 表示 Pod 内的一个容器。

字段：

- `image`：容器镜像；
- `resources`：资源请求。

在 faas-sim 中，一个函数副本通常会转换成一个 Pod，而这个 Pod 通常只有一个 Container。

## `PodSpec`

`PodSpec` 聚合容器列表和标签。

字段：

- `containers`：容器列表；
- `labels`：调度相关标签。

常见标签包括：

- `data.skippy.io/storage`
- `data.skippy.io/receives-from-storage`
- `data.skippy.io/receives-from-storage/path`
- `data.skippy.io/sends-to-storage`
- `data.skippy.io/sends-to-storage/path`
- `locality.skippy.io/type`
- `capability.skippy.io/...`

标签是 Skippy 扩展边缘调度语义的主要入口。

## `Pod`

`Pod` 是 Skippy 调度的基本单位。

字段：

- `name`：Pod 名称；
- `namespace`：命名空间；
- `spec`：PodSpec。

在 faas-sim 中，`sim/skippy.py:create_function_pod()` 会创建 Pod：

```python
pod = Pod(f"pod-{fd.name}-{cnt}", "faas-sim")
pod.spec = spec
```

## `Capacity`

`Capacity` 表示节点资源容量。

字段：

- `cpu_millis`
- `memory`

它既可以表示节点总容量，也可以表示节点剩余可分配资源。

## `Node`

`Node` 是调度器视角下的节点。

字段：

- `name`：节点名；
- `capacity`：总资源；
- `allocatable`：剩余资源；
- `labels`：节点标签；
- `pods`：已经放置到该节点的 Pod。

Skippy 调度成功后会调用：

```python
cluster_context.place_pod_on_node(pod, suggested_host)
```

该方法会：

- 把 Pod 加到 `node.pods`；
- 扣减 `node.allocatable.cpu_millis`；
- 扣减 `node.allocatable.memory`；
- 登记镜像缓存状态。

## `SchedulingResult`

调度结果是一个 `NamedTuple`：

```python
SchedulingResult(
    suggested_host: Node,
    feasible_nodes: int,
    needed_images: List[str],
)
```

字段含义：

- `suggested_host`：最终选中的节点；没有可行节点时为 `None`；
- `feasible_nodes`：通过谓词过滤的节点数量；
- `needed_images`：目标节点缺失、部署阶段需要拉取的镜像。

faas-sim 会读取 `suggested_host` 设置副本运行节点，读取 `needed_images` 决定镜像拉取行为。

