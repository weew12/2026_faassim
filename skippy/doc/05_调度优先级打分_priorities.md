# 05 · 调度优先级打分 (`core/priorities.py`)

> 解析文件：`skippy/core/priorities.py`（400 行）
>
> 优先级函数对应调度流程中的**打分阶段**：经过谓词过滤后的可行节点，会根据多个优先级函数计算分数。调度器对各优先级函数的分数乘以权重并求和，最终选择总分最高的节点作为建议放置位置。
>
> 本文件既包含 Kubernetes 默认调度器思想中的**资源均衡、镜像本地性**，也包含 Skippy 面向**边缘 / 数据密集型场景扩展**的数据本地性、位置类型和硬件能力评分。

## 1. 抽象基类：`Priority`

```python
class Priority:
    def map_node_score(self, context, pod, node) -> int:
        raise NotImplementedError

    def reduce_mapped_score(self, context, pod, nodes, node_scores) -> [int]:
        return node_scores   # 默认实现不改变分数
```

Kubernetes 风格的**两阶段打分**：

| 阶段 | 方法 | 作用 |
| --- | --- | --- |
| map | `map_node_score(context, pod, node)` | 对**单个候选节点**计算原始分数或代价。 |
| reduce | `reduce_mapped_score(context, pod, nodes, node_scores)` | 基于**所有候选节点**结果做归一化或反向缩放。 |

## 2. 缩放工具函数

### 2.1 `_scale_scores(scores, t_max=10)`

```python
def _scale_scores(scores, t_max=10):
    r_min = min(scores, default=0)
    r_max = max(scores, default=0)
    div = r_max - r_min
    if div == 0:
        return [0] * len(scores)
    return [int(((x - r_min) / div) * t_max) for x in scores]
```

- 把原始分数线性缩放到 `[0, t_max]`；
- 适用于「越大越好」的指标（如能力匹配数）。

### 2.2 `_scale_scores_inverse(scores, t_max=10)`

```python
def _scale_scores_inverse(scores, t_max=10):
    r_min = min(scores, default=0)
    r_max = max(scores, default=0)
    div = r_min - r_max
    if div == 0:
        return [0] * len(scores)
    return [int(((x - r_max) / div) * t_max) for x in scores]
```

- 把原始**代价**反向缩放到 `[t_max, 0]`；
- 适用于「越小越好」的指标（如传输时间）。

## 3. 优先级函数一览

| 类 | 父类 | 打分指标方向 | 关键字段/参数 | 与默认调度器的关系 |
| --- | --- | --- | --- | --- |
| `EqualPriority` | `Priority` | 越大越好 | 固定返回 1 | 占位/基线，未在默认调度器中使用 |
| `ImageLocalityPriority` | `Priority` | 越大越好 | `min_threshold=23MB`, `max_threshold=1000MB` | 旧版镜像本地性；目前默认调度器未启用 |
| `ResourcePriority` | `Priority` | 抽象 | 暴露 `scorer(...)` 给子类 | 抽象基类 |
| `BalancedResourcePriority` | `ResourcePriority` | 越大越好 | — | **默认启用**，权重 1.0 |
| `LocalityTypePriority` | `Priority` | 越大越好 | `locality.skippy.io/type` 标签 | **默认启用**，权重 1.0 |
| `CapabilityPriority` | `Priority` | 越大越好 | `capability.skippy.io/*` 标签 | **默认启用**，权重 1.0 |
| `LocalityPriority` | `Priority` | 抽象 | 暴露 `get_size` / `get_target_node` 给子类 | 抽象基类 |
| `LatencyAwareImageLocalityPriority` | `LocalityPriority` | 越小越好 → 反向缩放 | 镜像仓库固定为 `'registry'` | **默认启用**，权重 1.0 |
| `DataLocalityPriority` | `Priority` | 越小越好 → 反向缩放 | Pod 标签 `data.skippy.io/{receives-from,sends-to}-storage/path` | **默认启用**，权重 1.0 |

默认调度器组合（来自 `scheduler.py`）：

```python
default_priorities = [
    (1.0, BalancedResourcePriority()),
    (1.0, LatencyAwareImageLocalityPriority()),
    (1.0, LocalityTypePriority()),
    (1.0, DataLocalityPriority()),
    (1.0, CapabilityPriority()),
]
```

## 4. `EqualPriority` — 占位优先级

```python
class EqualPriority(Priority):
    def map_node_score(self, context, pod, node) -> int:
        return 1
```

返回固定分数 1。常用于基线或调试。

## 5. `ImageLocalityPriority` — 镜像本地性（K8s 风格）

### 5.1 业务作用

倾向选择已经缓存目标镜像的节点，减少部署阶段拉取镜像的网络传输和冷启动等待。与 Kubernetes `ImageLocalityPriority` 思路一致：**节点已有镜像越大、镜像分布越广，本地命中价值越高**。

### 5.2 关键参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `mb` | `1024*1024` | 字节换算基础单位。 |
| `min_threshold` | `23 MB` | 小于该阈值的本地性收益按最小阈值处理。 |
| `max_threshold` | `1000 MB` | 大于该阈值的本地性收益按最大阈值截断。 |

### 5.3 关键代码

```python
def scaled_image_score(self, node, image_state, total_num_nodes) -> int:
    spread = float(image_state.num_nodes) / float(total_num_nodes)
    return int(float(image_state.size[node.labels['beta.kubernetes.io/arch']]) * spread)
```

> **设计权衡**：用 `image_state.num_nodes / total_num_nodes` 作扩散比例。如果镜像已经分布在所有节点，则 spread=1，单镜像收益 = 镜像大小；若仅在少数节点有，则 spread 较小，收益被压缩。该值随后在 `calculate_priority` 中按 min/max 阈值线性映射到 `[0, context.max_priority]`。

### 5.4 注意

- **未在默认调度器中启用**——默认调度器用的是 `LatencyAwareImageLocalityPriority`，会同时考虑拉取时间代价；
- 本类可单独作为基线镜像本地性策略使用。

## 6. `ResourcePriority` / `BalancedResourcePriority` — 资源均衡

### 6.1 业务作用

`ResourcePriority` 是抽象基类：累加 Pod 的 CPU/内存请求总量，并把请求量与节点剩余资源交给子类的 `scorer`。

`BalancedResourcePriority` 是它的具体实现，倾向选择 **CPU 与内存占用比例更均衡**的节点，避免某一类资源先被耗尽而另一类资源大量闲置。

### 6.2 关键代码

```python
class BalancedResourcePriority(ResourcePriority):
    def scorer(self, context, requested, allocatable):
        cpu_fraction    = self.fraction_of_capacity(requested.cpu_millis, allocatable.cpu_millis)
        memory_fraction = self.fraction_of_capacity(requested.memory,      allocatable.memory)
        if cpu_fraction >= 1 or memory_fraction >= 1:
            return 0
        diff = fabs(cpu_fraction - memory_fraction)
        result = int((1 - diff) * float(context.max_priority))
        return result

    @staticmethod
    def fraction_of_capacity(requested, capacity):
        if capacity == 0:
            capacity = 1
        return float(requested) / float(capacity)
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **任一维度满载 → 0 分** | `cpu_fraction >= 1 or memory_fraction >= 1` 时直接返回 0，避免「内存剩余但 CPU 已满」的节点被优先选择。 |
| **`(1 - diff) * max_priority`** | `diff` 越小（CPU/内存占比越接近）分数越高。 |
| **容量为 0 兜底** | `fraction_of_capacity` 中 `if capacity == 0: capacity = 1` 避免除零——表示「节点无可分配资源」也应给 0 分。 |

## 7. `LocalityTypePriority` — 节点位置类型

### 7.1 业务作用

倾向选择带有 `locality.skippy.io/type=edge` 标签的**边缘节点**，弱化云节点优先级。该策略适合「边缘优先执行」的 serverless edge 场景。

### 7.2 关键代码

```python
class LocalityTypePriority(Priority):
    def map_node_score(self, context, pod, node) -> int:
        priority_mapping: Dict[str, int] = {
            'edge':  context.max_priority,
            'cloud': 0
        }
        try:
            return priority_mapping.get(node.labels['locality.skippy.io/type'], 0)
        except KeyError:
            return 0
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **`edge` 直接给满分** | 边缘优先策略下不再细分。 |
| **无标签 → 0 分** | 未声明位置类型的节点不被鼓励。 |
| **不需要 reduce** | map 已返回 `[0, max_priority]` 区间内的分数。 |

## 8. `CapabilityPriority` — 硬件 / 能力匹配

### 8.1 业务作用

检查节点是否具备 Pod 标签声明的能力（GPU / TPU / 其他边缘设备能力）。匹配项越多，原始分越高；随后通过 reduce 阶段缩放到统一评分范围。

### 8.2 关键代码

```python
class CapabilityPriority(Priority):
    def map_node_score(self, context, pod, node) -> int:
        priority = 0
        # 只取节点上 skippy 能力标签，避免普通标签干扰能力匹配
        pod_caps = dict(filter(lambda label: 'capability.skippy.io' in label[0], node.labels.items()))
        for capability in pod_caps.items():
            if capability[0] in pod.spec.labels and capability[1] == pod.spec.labels[capability[0]]:
                priority += 1
        return priority

    def reduce_mapped_score(self, context, pod, nodes, node_scores) -> [int]:
        return _scale_scores(node_scores, context.max_priority)
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **节点标签驱动而非 Pod 标签驱动** | 迭代的是 `node.labels` 中的 `capability.skippy.io/*`，过滤掉普通调度标签（如 `data.skippy.io/storage`）。 |
| **匹配键 + 匹配值** | 同时校验「能力键存在于 Pod 标签」**和**「值相等」，确保「Pod 需要 amd64 GPU，节点确实提供 amd64 GPU」才算匹配。 |
| **`_scale_scores` 归一化** | 能力匹配数差异巨大（0~N），必须线性缩放到 `[0, max_priority]` 才能和其他优先级函数加权求和。 |

> **实现注记**：第 227 行 `filter` 用法把 `node.labels.items()` 转为 `(key, value)` 元组流，再过滤键中含 `capability.skippy.io` 的项。这是 Python 3 中典型的「键过滤」技巧。

## 9. `LocalityPriority` — 本地性 / 距离类基类

### 9.1 业务作用

将「**需要传输的数据量**」和「**目标传输路径带宽**」转换为传输时间代价。子类分别定义传输对象大小和目标节点，例如镜像仓库、输入数据存储节点或输出数据存储节点。

### 9.2 关键代码

```python
class LocalityPriority(Priority):
    def map_node_score(self, context, pod, node) -> int:
        size = self.get_size(context, pod, node)
        target_node = self.get_target_node(context, pod, node)
        # 下载方向：从目标节点到候选执行节点的传输，如 registry -> worker
        bandwidth = context.get_dl_bandwidth(target_node, node.name)
        time = int(size / bandwidth)
        return time

    def reduce_mapped_score(self, context, pod, nodes, node_scores) -> [int]:
        # 传输时间越小越好 → 反向缩放
        min_count = min(node_scores, default=0)
        max_count = max(node_scores, default=0)
        if max_count == 0:
            return [0] * len(node_scores)
        return [int(context.max_priority * (max_count - n + min_count) / max_count)
                for n in node_scores]

    def get_target_node(self, context, pod, node) -> str: raise NotImplemented()
    def get_size(self, context, pod, node) -> int:        raise NotImplemented()
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **map 返回传输时间** | 原始打分是「越小越好」的代价指标。 |
| **reduce 反向缩放** | 自定义实现把 `min` 拉到 `max_priority`、`max` 拉到 `min`，是「代价 → 优先级」的标准做法。 |
| **`max_count == 0` 全 0** | 所有节点代价都为 0（无数据需传输）时，不做无意义的缩放。 |

## 10. `LatencyAwareImageLocalityPriority` — 带宽感知镜像本地性

### 10.1 业务作用

不仅判断节点是否已有镜像，还根据**镜像仓库到候选节点的带宽**估算拉取缺失镜像的时间。对于边缘环境中链路差异明显的场景，该函数比单纯 `ImageLocality` 更能体现部署代价。

### 10.2 关键代码

```python
def get_size(self, context, pod, node) -> int:
    size = 0
    node_arch = node.labels['beta.kubernetes.io/arch']
    for container in pod.spec.containers:
        image_name = normalize_image_name(container.image)
        if image_name in context.images_on_nodes[node.name]:
            continue   # 已有镜像 → 跳过
        image_states = context.get_image_state(image_name)
        if node_arch not in image_states.size:
            replacement = list(image_states.size.keys())[0]
            logger.error("could not resolve node arch '%s' for image '%s', estimating using '%s' instead",
                         node_arch, image_name, replacement)
            node_arch = replacement
        size += context.get_image_state(image_name).size[node_arch]
    return size

def get_target_node(self, context, pod, node) -> str:
    return 'registry'
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **`'registry'` 固定源** | 镜像仓库节点固定名为 `registry`，需在 `bandwidth` 图中预先注册该节点。 |
| **架构缺失兜底** | 镜像没有目标架构大小记录时，记 ERROR 日志并用镜像表中的第一个架构替代——避免调度崩溃。 |
| **求和所有容器** | Pod 内多容器场景下累加所有缺失镜像的大小。 |
| **reduce 用父类实现** | 直接复用 `LocalityPriority.reduce_mapped_score` 的反向缩放逻辑。 |

## 11. `DataLocalityPriority` — 数据本地性

### 11.1 业务作用

面向**数据密集型 Serverless Edge** 场景，估算函数**输入数据读取**和**输出数据写回**的网络传输时间。候选节点距离数据所在存储节点越近、带宽越高，传输时间越短，最终得分越高。

Pod 通过标签声明数据路径：

```text
data.skippy.io/receives-from-storage/path = <bucket>/<object>   # 需要读取
data.skippy.io/sends-to-storage/path      = <bucket>/<object>   # 需要写回
```

### 11.2 关键代码

```python
def map_node_score(self, context, pod, node) -> int:
    total_time = 0
    total_time += self.calculate_recv_time(context, pod, node)
    total_time += self.calculate_send_time(context, pod, node)
    return total_time

def calculate_recv_time(self, context, pod, node):
    path = pod.spec.labels.get('data.skippy.io/receives-from-storage/path')
    if not path: return 0
    data_item = context.storage_index.stat(*path.split('/'))
    if not data_item: return 0
    storage_nodes = context.get_storage_nodes(path)
    # 在保存该对象的存储节点中，选到候选节点方向带宽最小的路径作为保守估计
    min_bw_storage, min_bw = None, float('inf')
    for storage in storage_nodes:
        if storage == node.name: return 0    # 同节点 → 零传输
        bandwidth = context.get_dl_bandwidth(storage, node.name)
        if bandwidth < min_bw:
            min_bw, min_bw_storage = bandwidth, storage
    if min_bw_storage:
        return int(data_item.size / min_bw)
    return 0

def calculate_send_time(self, context, pod, node):
    path = pod.spec.labels.get('data.skippy.io/sends-to-storage/path')
    if not path: return 0
    data_item = context.storage_index.stat(*path.split('/'))
    if not data_item: return 0
    storage_nodes = context.get_storage_nodes(path)
    # 注意方向：candidate → storage（写回方向）
    min_bw_storage, min_bw = None, float('inf')
    for storage in storage_nodes:
        if storage == node.name: return 0
        bandwidth = context.get_dl_bandwidth(node.name, storage)   # 方向与 recv 相反
        if bandwidth < min_bw:
            min_bw, min_bw_storage = bandwidth, storage
    if min_bw_storage:
        return int(data_item.size / min_bw)
    return 0

def reduce_mapped_score(self, context, pod, nodes, node_scores) -> [int]:
    return _scale_scores_inverse(node_scores, context.max_priority)
```

### 11.3 设计要点

| 要点 | 说明 |
| --- | --- |
| **当前模型假设每个函数至多声明一个输入对象和一个输出对象** | 通过单一标签路径表达。 |
| **`stat(*path.split('/'))`** | 把 `bucket/object` 拆成 `(bucket, object)` 两参元组传给 `StorageIndex.stat`。 |
| **`min_bw` 选最差路径** | 用所有存储节点中**带宽最小**的链路估计传输时间，是保守估计——保证数据能在最坏路径上也能在合理时间内传输完成。 |
| **recv / send 方向相反** | `recv` 是 `storage → node`（下载方向），`send` 是 `node → storage`（上传方向）；`get_dl_bandwidth` 接收的恰好是「下载方向 from→to」参数，所以 send 要传 `(node.name, storage)`。 |
| **reduce 用 `_scale_scores_inverse`** | 传输时间越小越好，需要反向缩放。 |

## 12. 跨模块依赖

| 引用来源 | 使用的成员 |
| --- | --- |
| `scheduler.py` | `BalancedResourcePriority`, `LatencyAwareImageLocalityPriority`, `CapabilityPriority`, `DataLocalityPriority`, `LocalityTypePriority` |
| `clustercontext.py` | `list_nodes`, `images_on_nodes`, `get_image_state`, `get_dl_bandwidth`, `get_storage_nodes`, `storage_index` |
| `model.py` | `Pod`, `Node`, `Capacity`, `ImageState` |
| `utils.py` | `normalize_image_name` |
