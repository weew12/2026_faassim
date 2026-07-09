# 06 · 调度器主流程 (`core/scheduler.py`)

> 解析文件：`skippy/core/scheduler.py`（188 行）
>
> 本文件实现一个**轻量 Kubernetes 风格调度器**：
>
> 1. 从 `ClusterContext` 获取候选节点；
> 2. 执行**谓词过滤**，得到资源和标签约束均满足的可行节点；
> 3. 对可行节点执行**多个优先级函数**；
> 4. 将各优先级分数按**权重求和**；
> 5. 选择总分最高的节点，并更新 `ClusterContext` 中的 Pod 放置、节点剩余资源和镜像缓存状态。
>
> 在 faas-sim 中，`DefaultFaasSystem` 创建函数副本后，会通过 `sim/skippy.py` 构造 Pod，再调用本调度器决定函数副本部署在哪个 Ether/Skippy 节点上。

## 1. 类成员一览

```text
Scheduler
├── class attributes
│   ├── default_predicates: List[Predicate]
│   ├── default_priorities:  List[Tuple[float, Priority]]
│   ├── min_feasible_nodes_to_find = 100
│   ├── min_feasible_nodes_percentage_to_find = 5
│   └── default_percentage_of_nodes_to_score = 50
├── instance attributes
│   ├── predicates: List[Predicate]
│   ├── priorities:  List[Tuple[float, Priority]]
│   ├── percentage_of_nodes_to_score: int
│   ├── cluster_context: ClusterContext
│   └── last_scored_node_index: int
└── methods
    ├── schedule(pod) -> SchedulingResult
    ├── passes_predicates(pod, node) -> bool
    └── __num_feasible_nodes_to_find(num_all_nodes) -> int
```

## 2. 默认配置

### 2.1 默认谓词

```python
default_predicates: List[Predicate] = [
    PodFitsResourcesPred(),
    CheckNodeLabelPresencePred(['data.skippy.io/storage'], False)
]
```

| 谓词 | 作用 |
| --- | --- |
| `PodFitsResourcesPred` | 节点剩余 CPU/内存足以承载 Pod。 |
| `CheckNodeLabelPresencePred(['data.skippy.io/storage'], False)` | 节点**不应**包含 `data.skippy.io/storage` 标签——避免把普通函数放到存储专用节点。 |

### 2.2 默认优先级

```python
default_priorities: List[Tuple[float, Priority]] = [
    (1.0, BalancedResourcePriority()),
    (1.0, LatencyAwareImageLocalityPriority()),
    (1.0, LocalityTypePriority()),
    (1.0, DataLocalityPriority()),
    (1.0, CapabilityPriority()),
]
```

每个优先级权重均为 1.0，最终分数 = 各原始分（reduce 后）× 权重 之和。

### 2.3 Kubernetes 风格参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `min_feasible_nodes_to_find` | `100` | 至少寻找的可行节点数量。 |
| `min_feasible_nodes_percentage_to_find` | `5` | 至少寻找的可行节点比例（%）。 |
| `default_percentage_of_nodes_to_score` | `50` | 默认参与打分的节点比例（%）。 |

> 这三个参数主要影响**大规模集群**——避免对所有节点都跑全量打分。faas-sim 实验通常集群规模较小，效果上几乎等价于「打分所有可行节点」。

## 3. 构造函数 `__init__`

```python
def __init__(self, cluster_context, percentage_of_nodes_to_score=100,
             predicates=None, priorities=None):
    if priorities is None: priorities = self.default_priorities
    if predicates is None: predicates = self.default_predicates
    self.predicates = predicates
    self.priorities = priorities
    self.percentage_of_nodes_to_score = percentage_of_nodes_to_score
    self.cluster_context = cluster_context
    self.last_scored_node_index = 0
```

| 参数 | 说明 |
| --- | --- |
| `cluster_context` | 集群运行态上下文；提供节点、资源、镜像、带宽和存储索引。 |
| `percentage_of_nodes_to_score` | 通过过滤后参与打分的节点比例；faas-sim 默认传 100，即全打分。 |
| `predicates` | 自定义谓词集合；为 None 时使用 `default_predicates`。 |
| `priorities` | 自定义优先级集合（`(权重, Priority)` 元组列表）；为 None 时使用 `default_priorities`。 |
| `last_scored_node_index` | 上一轮可行节点扫描停止位置；下一轮从这里继续，避免始终从第一个节点开始造成偏置。 |

## 4. 主流程：`schedule(pod)`

### 4.1 流程图

```text
schedule(pod)
  │
  ├─ nodes = cluster_context.list_nodes()
  ├─ num_of_nodes_to_find = __num_feasible_nodes_to_find(len(nodes))
  │
  ├─ 过滤阶段
  │   filtered = filter(node → passes_predicates(pod, node),
  │                     islice(cycle(nodes),
  │                            last_scored_node_index,
  │                            last_scored_node_index + len(nodes)))
  │   feasible_nodes = list(islice(filtered, num_of_nodes_to_find))
  │   if feasible_nodes:
  │       last_scored_node_index = (nodes.index(feasible_nodes[-1]) + 1) % len(nodes)
  │
  ├─ 打分阶段（每个优先级函数做 map → reduce → 加权累加）
  │   scored_nodes = [0] * len(feasible_nodes)
  │   for weight, function in priorities:
  │       mapped   = [function.map_node_score(cluster, pod, n) for n in feasible_nodes]
  │       reduced  = function.reduce_mapped_score(cluster, pod, feasible_nodes, mapped)
  │       weighted = [s * weight for s in reduced]
  │       scored_nodes = list(map(add, weighted, scored_nodes))
  │
  ├─ 选分：sorted_scored_nodes = max(zip(feasible_nodes, scored_nodes), key=itemgetter(1))
  ├─ suggested_host = next(iter(sorted_scored_nodes), None)
  │
  └─ 状态写回
      if suggested_host:
          needed_images = [...]
          cluster_context.place_pod_on_node(pod, suggested_host)
      return SchedulingResult(suggested_host, len(feasible_nodes), needed_images)
```

### 4.2 关键代码

```python
def schedule(self, pod: Pod) -> SchedulingResult:
    logging.debug('Received a new pod to schedule: %s', pod.name)

    nodes = self.cluster_context.list_nodes()
    num_of_nodes_to_find = self.__num_feasible_nodes_to_find(len(nodes))

    # 从 last_scored_node_index 开始循环扫描节点，找到满足所有谓词的候选节点
    filtered = filter(lambda node: self.passes_predicates(pod, node),
                      islice(cycle(nodes),
                             self.last_scored_node_index,
                             self.last_scored_node_index + len(nodes)))
    feasible_nodes: [Node] = list(islice(filtered, num_of_nodes_to_find))
    if len(feasible_nodes) > 0:
        self.last_scored_node_index = (nodes.index(feasible_nodes[-1]) + 1) % len(nodes)

    cluster = self.cluster_context

    # 对所有可行节点执行加权优先级打分
    scored_nodes: [int] = [0] * len(feasible_nodes)
    for weighted_priority in self.priorities:
        weight = weighted_priority[0]
        function = weighted_priority[1]
        mapped_nodes = [function.map_node_score(cluster, pod, node) for node in feasible_nodes]
        reduced_node_scores = function.reduce_mapped_score(cluster, pod, feasible_nodes, mapped_nodes)
        weighted_node_scores = [score * weight for score in reduced_node_scores]
        scored_nodes = list(map(add, weighted_node_scores, scored_nodes))

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Pod %s / %s: %s', pod.name, type(function), weighted_node_scores)

    scored_named_nodes: [(Node, int)] = list(zip(feasible_nodes, scored_nodes))
    logging.debug('Node scores: %s', scored_named_nodes)

    # 选择总分最高的节点；没有可行节点时 suggested_host 为 None
    sorted_scored_nodes = max(scored_named_nodes, key=itemgetter(1), default=(None, 0))
    suggested_host: Node = next(iter(sorted_scored_nodes), None)
    needed_images = None

    if suggested_host is not None:
        # 在写回调度状态之前，记录目标节点尚未缓存的镜像
        needed_images = []
        host_images = self.cluster_context.images_on_nodes[suggested_host.name]
        for container in pod.spec.containers:
            if normalize_image_name(container.image) not in host_images:
                needed_images.append(normalize_image_name(container.image))

        # 将调度结果写回上下文：扣减资源、登记 Pod、更新镜像缓存表
        self.cluster_context.place_pod_on_node(pod, suggested_host)
        logging.debug('Found best node. Remaining allocatable resources after scheduling: %s',
                      suggested_host.allocatable)

    return SchedulingResult(suggested_host=suggested_host,
                            feasible_nodes=len(feasible_nodes),
                            needed_images=needed_images)
```

### 4.3 设计要点

| 要点 | 说明 |
| --- | --- |
| **`cycle(nodes)` + `islice`** | 循环遍历节点列表，从 `last_scored_node_index` 起走过 `len(nodes)` 步，避免每次都从头开始造成调度偏置。 |
| **`__num_feasible_nodes_to_find` 限流** | 大集群下不全量打分；faas-sim 集群规模小时通常退回「全打分」。 |
| **map → reduce → 加权** | 严格遵循 K8s 风格：先对每节点独立计算原始分，再做跨节点归一化（reduce），最后按权重累加。 |
| **`max(..., default=(None, 0))`** | 没有可行节点时返回 `(None, 0)`，让 `suggested_host` 落空。 |
| **`needed_images` 在写回前计算** | 必须在 `place_pod_on_node` **之前**计算——因为它会更新 `images_on_nodes`，届时所有镜像都会显示为「已存在」。 |
| **状态写回 = 单步原子** | `place_pod_on_node` 同时扣资源 + 登记 Pod + 更新镜像缓存，faas-sim 后续依此推进生命周期。 |

### 4.4 注意点

- `suggested_host = next(iter(sorted_scored_nodes), None)` 这里 `sorted_scored_nodes` 实际上只是 `max()` 返回的**单个 `(Node, score)` 元组**，`next(iter(...))` 取的是这个元组本身。写法略绕，等价于 `suggested_host = sorted_scored_nodes[0]`（前提是 `feasible_nodes` 非空）。当 `feasible_nodes` 为空时 `max(...)` 走 `default=(None, 0)`，`next(iter((None, 0)))` 仍返回 `None`——结果一致。
- `default=(None, 0)` 的第二个元素 `0` 实际未使用，因为 `default` 的整体会被 `next(iter(...))` 当作单元素迭代。

## 5. `passes_predicates(pod, node)`

```python
def passes_predicates(self, pod: Pod, node: Node) -> bool:
    return all(self.__passes_and_logs_predicate(p, self.cluster_context, pod, node)
               for p in self.predicates)

def __passes_and_logs_predicate(self, predicate, context, pod, node):
    result = predicate.passes_predicate(context, pod, node)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f'Pod {pod.name} / Node {node.name} / {type(predicate).__name__}: '
                     f'{"Passed" if result else "Failed"}')
    return result
```

把所有谓词按 AND 组合；逐项 DEBUG 日志记录通过/失败状态。

## 6. `__num_feasible_nodes_to_find(num_all_nodes)`

```python
def __num_feasible_nodes_to_find(self, num_all_nodes: int) -> int:
    if num_all_nodes < self.min_feasible_nodes_percentage_to_find \
       or self.percentage_of_nodes_to_score >= 100:
        return num_all_nodes
    adaptive_percentage: float = self.percentage_of_nodes_to_score
    if adaptive_percentage <= 0:
        adaptive_percentage = self.default_percentage_of_nodes_to_score - num_all_nodes / 125
        if adaptive_percentage < self.min_feasible_nodes_percentage_to_find:
            adaptive_percentage = self.min_feasible_nodes_percentage_to_find
    num_nodes = int(num_all_nodes * adaptive_percentage / 100)
    if num_nodes < self.min_feasible_nodes_to_find:
        return self.min_feasible_nodes_to_find
    return num_nodes
```

### 6.1 行为分支

| 条件 | 返回值 |
| --- | --- |
| 集群规模太小（< `min_feasible_nodes_percentage_to_find`）或 `percentage_of_nodes_to_score >= 100` | `num_all_nodes`（全打分）。 |
| `percentage_of_nodes_to_score <= 0` | 用 `default_percentage_of_nodes_to_score - num_all_nodes / 125` 计算自适应比例，最低不低于 `min_feasible_nodes_percentage_to_find`。 |
| 上述都不是 | `num_all_nodes * adaptive_percentage / 100`，下限为 `min_feasible_nodes_to_find`。 |

### 6.2 设计要点

| 要点 | 说明 |
| --- | --- |
| **保留 K8s 思想** | 大集群下不全量打分，既支持完整打分，也支持降低调度开销。 |
| **faas-sim 实际行为** | 集群规模通常较小（< 100），`percentage_of_nodes_to_score=100`，因此几乎总是「全打分」。 |
| **最小节点数兜底** | `min_feasible_nodes_to_find=100` 保证大集群下也会收集到至少 100 个可行节点。 |

## 7. 跨模块依赖

| 引用来源 | 使用的成员 |
| --- | --- |
| `clustercontext.py` | `list_nodes`, `images_on_nodes`, `place_pod_on_node` |
| `model.py` | `Pod`, `Node`, `SchedulingResult` |
| `predicates.py` | `Predicate`, `PodFitsResourcesPred`, `CheckNodeLabelPresencePred` |
| `priorities.py` | `Priority`, `BalancedResourcePriority`, `LatencyAwareImageLocalityPriority`, `CapabilityPriority`, `DataLocalityPriority`, `LocalityTypePriority` |
| `utils.py` | `normalize_image_name` |

## 8. 完整调用链

```text
faas-sim sim/skippy.py
   └─ Scheduler.schedule(pod)
         ├─ cluster_context.list_nodes()
         ├─ passes_predicates(pod, node)            # 过滤
         │     ├─ PodFitsResourcesPred.passes_predicate
         │     └─ CheckNodeLabelPresencePred.passes_predicate
         ├─ for (weight, priority) in priorities:   # 打分
         │     ├─ priority.map_node_score(...)
         │     │     ├─ BalancedResourcePriority.scorer
         │     │     ├─ LatencyAwareImageLocalityPriority.{map_node_score, get_size, get_target_node}
         │     │     ├─ LocalityTypePriority.map_node_score
         │     │     ├─ DataLocalityPriority.{map_node_score, calculate_recv_time, calculate_send_time}
         │     │     └─ CapabilityPriority.{map_node_score, reduce_mapped_score}
         │     └─ priority.reduce_mapped_score(...)
         ├─ max(scored_named_nodes, key=itemgetter(1))
         ├─ cluster_context.images_on_nodes[host]   # 计算 needed_images
         └─ cluster_context.place_pod_on_node(pod, host)
               ├─ utils.normalize_image_name
               ├─ image_state.num_nodes += 1
               └─ node.allocatable.{cpu_millis, memory} -= 请求量
```
