# 03 · 集群运行态上下文 (`core/clustercontext.py`)

> 解析文件：`skippy/core/clustercontext.py`（193 行）
>
> 本文件定义调度器读取和更新集群运行态的统一接口。对应到 Kubernetes，可以把它理解为「调度器通过 API Server / etcd 看到的集群快照」；对应到 faas-sim，它由 `SimulationClusterContext` 实现，并把 Ether 拓扑、函数镜像仓库、对象存储索引和节点剩余资源暴露给 Skippy。
>
> `ClusterContext` 既是**只读查询入口**，也是**调度后的状态更新入口**：调度器选中节点后，会通过 `place_pod_on_node` 扣减节点可分配资源并登记镜像缓存状态；函数副本释放时，则通过 `remove_pod_from_node` 恢复资源。

## 1. 类型与字段概览

```text
ClusterContext (ABC)
├── image_states: Dict[str, ImageState]               # 镜像元数据表
├── max_priority: int = 10                           # 单个优先级函数的最高分
├── images_on_nodes: Dict[str, Dict[str, ImageState]] # 节点本地镜像缓存表
├── bandwidth: BandwidthGraph                        # 节点间带宽图
└── storage_index: StorageIndex | None               # 对象存储索引
```

`BandwidthGraph` 类型别名：

```python
BandwidthGraph = Dict[str, Dict[str, float]]
# bandwidth[from_node][to_node] = 从 from_node 到 to_node 的可用带宽（字节/秒）
```

## 2. 构造函数 `__init__`

```python
def __init__(self):
    self.image_states      = self.get_init_image_states()
    self.max_priority      = 10
    self.images_on_nodes   = defaultdict(dict)
    self.bandwidth         = self.get_bandwidth_graph()
    self.storage_index     = None
```

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| `image_states` | 镜像元数据表，键为规范化镜像名 | 子类 `get_init_image_states()` |
| `max_priority` | 单个优先级函数的最高分；与 Kubernetes 默认打分范围一致 | 写死 10 |
| `images_on_nodes` | 节点本地镜像缓存：`node_name -> {image_name: ImageState}` | 初始化为空字典 |
| `bandwidth` | 节点间带宽图 | 子类 `get_bandwidth_graph()` |
| `storage_index` | 对象存储索引 | 由 faas-sim benchmark 或拓扑初始化阶段注入 |

> `storage_index` 留空直到外部注入——这反映了「数据本地性只在数据密集型实验中出现」的实验设定。

## 3. 抽象接口（子类必须实现）

| 方法 | 返回 | 含义 |
| --- | --- | --- |
| `get_init_image_states()` | `Dict[str, ImageState]` | 仿真开始时已知的镜像元数据表（按架构登记镜像大小）。 |
| `get_bandwidth_graph()` | `Dict[str, Dict[str, float]]` | 节点间带宽图（用于镜像拉取 / 数据传输时间估算）。 |
| `list_nodes()` | `List[Node]` | 当前可参与调度的节点列表。 |
| `get_next_storage_node(node)` | `str` | 根据当前节点选择下一个可用的存储节点；具体策略由子类实现。 |

`get_node(name)` 提供按名查询的便捷实现：

```python
def get_node(self, name: str) -> Node:
    for node in self.list_nodes():
        if node.name == name:
            return node
    # 未找到时返回 None（注意：函数体没有显式 return）
```

## 4. 存储索引辅助方法

### 4.1 `get_storage_nodes(urn) -> List[str]`

返回保存指定对象的存储节点列表。

- `urn` 采用 `bucket/object` 路径形式；
- 当前实现假定同一 bucket 内的对象可从该 bucket 的所有存储节点读取；
- 委托给 `storage_index.get_bucket_nodes(bucket)`。

```python
def get_storage_nodes(self, urn: str) -> List[str]:
    bucket, name = urn.split('/')
    return [name for name in self.storage_index.get_bucket_nodes(bucket)]
```

### 4.2 与 `DataLocalityPriority` 的衔接

`priorities.DataLocalityPriority` 调用本方法获取存储节点列表，再结合 `get_dl_bandwidth` 估算数据传输时间。

## 5. 调度后状态更新：`place_pod_on_node`

### 5.1 关键流程

```python
def place_pod_on_node(self, pod: Pod, node: Node):
    for container in pod.spec.containers:
        image_name = normalize_image_name(container.image)

        # 1. 镜像首次出现在该节点 → 登记并递增镜像分布计数
        if image_name not in self.images_on_nodes[node.name]:
            image_state = self.get_image_state(image_name)
            image_state.num_nodes += 1
            images_on_nodes = self.images_on_nodes[node.name]
            images_on_nodes[image_name] = image_state
            self.images_on_nodes[node.name][image_name] = image_state

        # 2. 累加容器资源请求并扣减节点剩余资源
        required_cpu_millis = container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
        required_memory      = container.resources.requests.get('memory', container.resources.default_mem_request)
        node.allocatable.cpu_millis -= required_cpu_millis
        node.allocatable.memory      -= required_memory

    # 3. 登记 Pod 与节点的放置关系
    node.pods.append(pod)
```

### 5.2 设计要点

| 要点 | 说明 |
| --- | --- |
| **更新的是调度器内部状态** | 不代表真实容器已启动；faas-sim 后续还会模拟镜像拉取、容器启动、setup 和请求执行。 |
| **`normalize_image_name` 必先调用** | 避免 `foo` 与 `foo:latest` 被视为两个不同镜像导致本地性判断错误。 |
| **`image_state.num_nodes += 1`** | 同步影响后续 `ImageLocalityPriority` 的镜像扩散比例计算。 |
| **资源回退默认请求** | 用 `dict.get(key, default)`，容器未声明资源时使用 `ResourceRequirements.default_*` 占位。 |

> 代码中第 113–115 行存在冗余赋值（`images_on_nodes = self.images_on_nodes[node.name]` 然后又立即重新写入），无副作用但可清理。详见源码 `clustercontext.py:113-115`。

## 6. 释放与镜像清理

### 6.1 `remove_pod_from_node`

```python
def remove_pod_from_node(self, pod: Pod, node: Node):
    for container in pod.spec.containers:
        required_cpu_millis = container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
        required_memory      = container.resources.requests.get('memory', container.resources.default_mem_request)
        node.allocatable.cpu_millis += required_cpu_millis
        node.allocatable.memory      += required_memory
    node.pods.remove(pod)
```

- 用于函数副本**缩容或释放**时的调度状态回滚；
- **镜像缓存不删除**——容器退出后镜像通常仍可留在节点本地。

### 6.2 `remove_pod_images_from_node`

```python
def remove_pod_images_from_node(self, pod: Pod, node: Node):
    for container in pod.spec.containers:
        image_name = normalize_image_name(container.image)
        if image_name in self.images_on_nodes[node.name]:
            image_state = self.get_image_state(image_name)
            image_state.num_nodes -= 1
            del self.images_on_nodes[node.name][image_name]
```

- 用于**显式模拟镜像缓存清理或节点状态重置**；
- 调用后会降低 `image_state.num_nodes`，从而影响后续镜像本地性评分。

## 7. 镜像元数据获取

### 7.1 `get_image_state(image_name)`

```python
def get_image_state(self, image_name: str) -> ImageState:
    if self.image_states[image_name] is None:
        self.image_states[image_name] = self.retrieve_image_state(image_name)
    return self.image_states[image_name]
```

按需触发「远程元数据获取」扩展入口。当前 faas-sim 实验通常在启动前把镜像大小写入 `image_states`，因此默认不需要访问 Docker Registry。

### 7.2 `retrieve_image_state(image_name)`

```python
def retrieve_image_state(self, image_name):
    raise NotImplemented("Remote requested size information about images are not yet supported.")
```

> 当前实现是**抽象兜底**，未对接 Docker Registry。若后续要接入真实镜像仓库，可在子类中实现。

### 7.3 `get_image_sizes(pod, arch='amd64')`

返回 Pod 所需镜像在指定架构下的大小表：

```python
return {
    container.image: self.get_image_state(container.image).size[arch]
    for container in pod.spec.containers
}
```

供 `LatencyAwareImageLocalityPriority` 估算镜像拉取时间。

## 8. 带宽查询

### 8.1 `get_dl_bandwidth(from_node, to_node)`

```python
def get_dl_bandwidth(self, from_node: str, to_node: str) -> float:
    return self.bandwidth[from_node][to_node]
```

返回从 `from_node` 到 `to_node` 的**下载方向带宽**（字节/秒）。`LocalityPriority.map_node_score` 中用其计算传输时间 `time = size / bandwidth`。

## 9. 跨模块依赖

| 引用来源 | 使用的成员 |
| --- | --- |
| `scheduler.py` | `list_nodes`, `images_on_nodes`, `place_pod_on_node`, `get_dl_bandwidth` |
| `predicates.py` | 抽象基类声明里的 `ClusterContext`（运行时只用类型注解） |
| `priorities.py` | `list_nodes`, `images_on_nodes`, `get_image_state`, `get_image_sizes`, `get_dl_bandwidth`, `storage_index`, `get_storage_nodes` |
| `model.py` | 不引用本文件，但 `ClusterContext` 内部引用 `Node` / `Pod` / `ImageState` / `StorageIndex` |

## 10. 调用时序（一次调度涉及到的本类方法）

```text
Scheduler.schedule(pod)
   ├─ cluster_context.list_nodes()                  # 取候选节点
   ├─ cluster_context.get_image_state(image)        # 镜像大小（被优先级函数触发）
   ├─ cluster_context.get_image_sizes(pod, arch)    # 镜像大小表（被 LatencyAware 触发）
   ├─ cluster_context.images_on_nodes[host]         # 镜像本地性查询
   ├─ cluster_context.get_storage_nodes(path)       # 数据本地性查询
   ├─ cluster_context.get_dl_bandwidth(a, b)        # 带宽查询
   └─ cluster_context.place_pod_on_node(pod, host)  # 状态写回（扣资源 + 登记缓存）
```
