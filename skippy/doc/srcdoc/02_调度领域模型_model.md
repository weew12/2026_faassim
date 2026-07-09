# 02 · 调度领域模型 (`core/model.py`)

> 解析文件：`skippy/core/model.py`（231 行）
>
> 本文件定义 Skippy 调度器所需的**最小 Kubernetes 风格对象模型**。它不直接依赖 Kubernetes API，而是用纯 Python 对象表达调度决策需要的关键状态：节点容量、节点剩余资源、Pod 内容器镜像、容器资源请求、Pod 标签、调度结果。
>
> 在 faas-sim 中，`sim/skippy.py` 会把函数部署转换为 `Pod`，把 Ether 节点转换为 `Node`。随后 `Scheduler.schedule` 基于这些对象执行谓词过滤和优先级打分。

## 1. 类型全景

```text
调度结果                节点                   Pod                PodSpec               容器                资源请求
SchedulingResult ──  Node ──             ──  Pod  ──         ──  PodSpec ──       ──  Container ──           ──  ResourceRequirements
   suggested_host      │   name            │   name            │   containers       │   image               │   requests
   feasible_nodes      │   pods            │   namespace       │   labels           │   resources           │   (cpu / memory)
   needed_images       │   capacity        │   spec            │                    │   ResourceRequirements│
                       │   allocatable     │                   │                    │                       │
                       │   labels          │                   │                    │                       │
                       │                   │                   │                    │                       │
                       └─ Capacity         └───────────────────┴────────────────────┴─ 
                            cpu_millis
                            memory
                        (也用于累加容器请求)

辅助类型
   ImageState            
        size: Dict[arch, bytes]   # 各架构镜像大小
        num_nodes: int            # 已缓存该镜像的节点数
```

## 2. `ImageState` — 容器镜像运行态元数据

### 2.1 业务作用

- 记录**同一个逻辑镜像在不同 CPU 架构下**的镜像大小；
- 记录该镜像当前已经分布在多少个节点上；
- 支撑镜像本地性 / 带宽感知镜像本地性 优先级函数判断「把 Pod 放到某节点后是否需要额外拉镜像」。

### 2.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `size` | `Dict[str, int]` | 键为节点架构（如 `amd64`、`arm32v7`、`aarch64`），值为该架构镜像大小，单位字节。 |
| `num_nodes` | `int` | 当前已缓存该镜像的节点数量；衡量该镜像在集群中的扩散程度。 |

### 2.3 关键方法

- `__init__(size, num_nodes=0)`：保存多架构镜像大小表与初始节点数。
- `__str__` / `__repr__`：直接打印 `ImageState{...}` 形式，便于日志与调试。

### 2.4 关键代码（`priorities.py` 中如何读取 `size`）

```python
# 只取目标节点架构对应的镜像大小
return int(float(image_state.size[node.labels['beta.kubernetes.io/arch']]) * spread)
```

## 3. `ResourceRequirements` — 容器资源请求描述

### 3.1 业务作用

模拟 Kubernetes `resources.requests` 的核心语义。Skippy 只关心调度前的资源占位，因此这里主要记录 **CPU 与内存请求量**，并在资源谓词、资源均衡、带宽感知镜像本地性等优先级函数中使用。

### 3.2 默认值

```python
default_milli_cpu_request = 100         # 0.1 个 CPU 核
default_mem_request = 200 * 1024 * 1024 # 200 MB
default_requests = {"cpu": 100, "memory": 200MB}
```

> 设计理由：Kubernetes 调度器对未声明资源请求的容器会假设一个较小的非零占位，避免「完全零请求导致资源评分失真」。本实现沿用该思路。

### 3.3 关键代码

```python
def __init__(self, requests: Dict[str, float] = None) -> None:
    self.requests = requests or dict(ResourceRequirements.default_requests)
```

注意 `or dict(...)` 而不是直接 `requests or self.default_requests`，避免多个 `ResourceRequirements` 共享同一个可变 dict。

## 4. `Container` — Pod 内的容器描述

### 4.1 业务作用

调度器并不真正启动容器，而是用 `Container` 表达：

- 该 Pod 需要哪些**镜像**（`image`）；
- 该镜像需要占用多少**资源**（`resources`）。

在 faas-sim 中，一个函数副本通常会被转换为包含**一个容器**的 Pod；容器的 `image` 对应函数镜像，`resources` 对应函数容器资源需求。

### 4.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `resources` | `ResourceRequirements` | 资源请求对象；未显式传入时使用 `ResourceRequirements()` 默认值。 |
| `image` | `str` | 容器镜像名，可能是不带 tag 的名称；调度时会通过 `utils.normalize_image_name` 规范化。 |

## 5. `PodSpec` — Pod 规格描述

### 5.1 业务作用

聚合 Pod 的**容器列表**和**标签集合**。

- 容器列表 → 决定资源占用与镜像需求；
- 标签集合 → 承载数据本地性、能力需求、存储读写路径等调度信息。

faas-sim 的 `raith21` 实验扩展会在标签中写入：

```text
data.skippy.io/receives-from-storage/path = <bucket>/<object>
data.skippy.io/sends-to-storage/path      = <bucket>/<object>
```

供 `DataLocalityPriority` 计算数据传输代价。

### 5.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `containers` | `List[Container]` | Pod 内容器列表；Skippy 会逐个累加资源请求和镜像大小。 |
| `labels` | `Dict[str, str]` | Pod 标签字典；用于表达数据输入输出、硬件能力需求等调度约束或偏好。 |

### 5.3 关键代码

```python
def __init__(self, containers=None, labels=None):
    if containers is None: containers = []
    if labels is None:     labels = {}
    self.containers = containers
    self.labels = labels
```

注意用 `is None` 而非 `or []`：避免传入**本身为空的列表/字典**时被默认值覆盖。

## 6. `Pod` — 调度器视角下的 Pod

### 6.1 业务作用

`Pod` 是 Skippy 调度的基本单位。faas-sim 每创建一个函数副本，就会构造一个对应的 `Pod` 对象交给调度器。调度结果中的 `suggested_host` 表示这个 Pod 应当放置到哪个节点。

### 6.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `str` | Pod 名称；faas-sim 通常用函数副本名称或生成序号构造。 |
| `namespace` | `str` | 命名空间；用于保留 Kubernetes 风格对象结构。 |
| `spec` | `PodSpec` | Pod 规格，包含容器列表和调度标签。 |

## 7. `Capacity` — 节点容量 / 剩余可分配资源

### 7.1 业务作用

`Capacity` 既可表示节点**总容量**（`Node.capacity`），也可表示节点**当前剩余可分配资源**（`Node.allocatable`）。Skippy 在放置 Pod 时减少 `allocatable`，在移除 Pod 时恢复。

### 7.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `cpu_millis` | `int` | CPU 容量，单位 millicore；1000 表示 1 个核心。 |
| `memory` | `int` | 内存容量，单位字节。 |

### 7.3 关键代码

```python
def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1024 * 1024 * 1024):
    self.memory = memory
    self.cpu_millis = cpu_millis
```

默认 1 核 / 1 GB，作为未显式指定时的占位值。

## 8. `Node` — 调度器视角下的计算节点

### 8.1 业务作用

`Node` 表示 Kubernetes Worker / 边缘节点在调度器中的**简化模型**：

- 保存节点总容量、剩余资源、标签和已放置 Pod；
- 标签用于表达**架构、边缘/云位置、GPU/TPU 等能力**；
- 剩余资源用于**资源过滤和资源均衡评分**。

### 8.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `str` | 节点名称；需与 faas-sim / Ether 节点名称保持一致，便于跨模块关联。 |
| `pods` | `List[Pod]` | 已调度到该节点的 Pod 列表。 |
| `capacity` | `Capacity` | 节点总资源容量。 |
| `allocatable` | `Capacity` | 节点剩余可分配资源；运行态，会随 Pod 放置和移除动态变化。 |
| `labels` | `Dict[str, str]` | 节点标签，表达架构、位置、能力和存储角色等调度信息。 |

### 8.3 关键代码

```python
def __init__(self, name, capacity=None, allocatable=None, labels=None):
    self.name = name
    self.capacity = capacity or Capacity()
    self.allocatable = allocatable or Capacity()
    self.labels = labels or {}
    self.pods = list()
```

`pods = list()` 而非 `pods = []` —— 避免默认参数共享可变对象陷阱（即便这里用的是实例属性赋值，写 `list()` 更显式表达「每个实例独立一份列表」的意图）。

## 9. `SchedulingResult` — 调度结果（`NamedTuple`）

### 9.1 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `suggested_host` | `Node` | 最终建议放置 Pod 的节点；没有可行节点时为 `None`。 |
| `feasible_nodes` | `int` | 经谓词过滤后参与打分的可行节点数量。 |
| `needed_images` | `List[str]` | 目标节点尚未缓存、需要在部署阶段拉取的镜像名列表。 |

### 9.2 用法示例（`scheduler.py`）

```python
return SchedulingResult(
    suggested_host=suggested_host,
    feasible_nodes=len(feasible_nodes),
    needed_images=needed_images,
)
```

faas-sim 拿到该结果后：

- 用 `suggested_host` 在 Ether 拓扑中部署副本；
- 根据 `needed_images` 触发镜像拉取模拟；
- 用 `feasible_nodes` 写入调度日志。

## 10. 跨模块依赖

| 上游（本文件提供） | 下游（使用方） |
| --- | --- |
| `Node`, `Pod`, `Capacity`, `ImageState` | `clustercontext.py`（状态读写） |
| `Node`, `Pod`, `Capacity`, `ImageState` | `predicates.py`（过滤） |
| `Node`, `Pod`, `Capacity`, `ImageState` | `priorities.py`（打分） |
| `Node`, `Pod`, `SchedulingResult` | `scheduler.py`（主流程） |
