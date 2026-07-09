# 04 · 调度谓词过滤 (`core/predicates.py`)

> 解析文件：`skippy/core/predicates.py`（169 行）
>
> 谓词对应调度流程中的**过滤阶段**：在对节点打分之前，先判断一个 Pod 是否具备放置到某个节点上的**基本条件**。只有通过所有谓词的节点才会进入优先级打分。
>
> 当前内置谓词主要覆盖两类逻辑：
>
> 1. **资源充足性**：节点剩余 CPU/内存是否能承载 Pod；
> 2. **标签存在性**：节点是否包含或不包含某些标签，例如避免把普通函数调度到存储专用节点。

## 1. 类继承图

```text
Predicate (ABC)
├── CombinedPredicate
│   ├── NonCriticalPreds      # 仅资源充足性
│   ├── EssentialPreds        # 仅资源充足性
│   └── GeneralPreds          # EssentialPreds ∩ NonCriticalPreds
├── PodFitsResourcesPred      # 资源充足性
└── CheckNodeLabelPresencePred  # 标签存在性（has_labels / has_labels_not）
```

## 2. 基类：`Predicate`

```python
class Predicate:
    def __init__(self):
        pass

    def passes_predicate(self, context: ClusterContext, pod: Pod, node: Node) -> bool:
        raise NotImplementedError
```

- 子类必须实现 `passes_predicate`；
- 返回 `True` 表示 Pod 可以继续考虑该节点，`False` 表示该节点在过滤阶段被排除。

## 3. `CombinedPredicate` — 组合谓词

### 3.1 业务作用

将多个谓词按**逻辑与**组合：只有所有子谓词均通过时才返回通过。该类用于构造 `GeneralPreds`、`EssentialPreds` 等 Kubernetes 风格的谓词集合。

### 3.2 关键实现

```python
class CombinedPredicate(Predicate):
    def __init__(self, predicates: [Predicate]):
        super().__init__()
        self.predicates = predicates

    def passes_predicate(self, context, pod, node) -> bool:
        return all(self.__passes_and_logs_predicate(p, context, pod, node)
                   for p in self.predicates)

    def __passes_and_logs_predicate(self, predicate, context, pod, node):
        result = predicate.passes_predicate(context, pod, node)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'Pod {pod.name} / Node {node.name} / {type(predicate).__name__}: '
                         f'{"Passed" if result else "Failed"}')
        return result
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **`all(...)` 短路** | 任一子谓词失败立即返回 `False`，避免无效打分计算。 |
| **逐项日志** | DEBUG 模式下单独记录每个子谓词的通过/失败，方便定位「为什么这个节点被过滤掉」。 |
| **不存累计分** | 谓词只关心布尔结果，**打分由优先级函数负责**——这是 K8s 风格「filter → score」的标准划分。 |

## 4. `PodFitsResourcesPred` — 资源充足性谓词

### 4.1 业务作用

计算 Pod 中所有容器声明的 CPU/内存请求总和，并与目标节点的剩余可分配资源比较。若请求量不超过节点剩余资源，则该节点可承载该 Pod；否则在过滤阶段被排除。

### 4.2 关键代码

```python
def passes_predicate(self, context, pod, node) -> bool:
    allocatable = node.allocatable
    requested = Capacity(0, 0)
    for container in pod.spec.containers:
        requested.cpu_millis += container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
        requested.memory      += container.resources.requests.get('memory', container.resources.default_mem_request)
    passed = requested.memory <= allocatable.memory and requested.cpu_millis <= allocatable.cpu_millis
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f'Pod {pod.name} requests {requested.cpu_millis} / {requested.memory}. '
                     f'Available on node {node.name}: {allocatable.cpu_millis} / {allocatable.memory}. '
                     f'Passed: {passed}')
    return passed
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **CPU 与内存同时满足** | 任一维度不满足即失败，避免节点只够内存但 CPU 已被耗尽的「伪可行」结果。 |
| **请求缺省值兜底** | 容器未声明 CPU/内存时使用 `ResourceRequirements.default_milli_cpu_request` / `default_mem_request` 占位（100 millicore / 200 MB）。 |
| **`node.allocatable`** | 用 `allocatable` 而非 `capacity`，避免重复扣减已被占用的资源。 |

## 5. 谓词集合：`NonCriticalPreds` / `EssentialPreds` / `GeneralPreds`

```python
class NonCriticalPreds(CombinedPredicate):
    def __init__(self):
        super().__init__([PodFitsResourcesPred()])

class EssentialPreds(CombinedPredicate):
    def __init__(self):
        super().__init__([PodFitsResourcesPred()])

class GeneralPreds(CombinedPredicate):
    def __init__(self):
        super().__init__([EssentialPreds(), NonCriticalPreds()])
```

| 集合 | 子谓词 | 用途 |
| --- | --- | --- |
| `EssentialPreds` | 仅 `PodFitsResourcesPred` | 基础谓词集合。 |
| `NonCriticalPreds` | 仅 `PodFitsResourcesPred` | 非关键 Pod 谓词集合。 |
| `GeneralPreds` | `EssentialPreds` ∧ `NonCriticalPreds` | 通用谓词集合。 |

> **实现注记**：faas-sim 当前没有「关键 Pod / 非关键 Pod」概念，`EssentialPreds` 和 `NonCriticalPreds` 退化为同一个内容；`GeneralPreds` 因此相当于「两个相同的资源谓词做 AND」，结果是「资源检查 ×2」。这是 Kubernetes 风格在 faas-sim 简化场景下的退化形式，**不会引入额外约束**。

## 6. `CheckNodeLabelPresencePred` — 节点标签存在性谓词

### 6.1 业务作用

判断目标节点是否必须包含或必须不包含某些标签。默认调度器使用该谓词避免把普通函数 Pod 放到带有 `data.skippy.io/storage` 标签的存储节点上。

### 6.2 关键代码

```python
class CheckNodeLabelPresencePred(Predicate):
    def __init__(self, labels: List[str], should_be_present=True) -> None:
        super().__init__()
        self.labels = labels
        self.should_be_present = should_be_present
        # 根据模式绑定具体检查函数，避免 passes_predicate 中反复分支判断
        if should_be_present:
            self._passes_predicate = self.has_labels
        else:
            self._passes_predicate = self.has_labels_not

    def passes_predicate(self, context, pod, node) -> bool:
        return self._passes_predicate(node)

    def has_labels(self, node: Node) -> bool:
        for label in self.labels:
            if label not in node.labels:
                return False
        return True

    def has_labels_not(self, node: Node) -> bool:
        for label in self.labels:
            if label in node.labels:
                return False
        return True
```

设计要点：

| 要点 | 说明 |
| --- | --- |
| **二选一绑定** | 在 `__init__` 中按 `should_be_present` 把 `_passes_predicate` 绑定到 `has_labels` 或 `has_labels_not`，运行时不再分支判断。 |
| **AND 语义** | `has_labels`：要求**所有**指定标签都存在；`has_labels_not`：要求**所有**指定标签都不存在。 |

### 6.3 与默认调度器的关系

`Scheduler.default_predicates` 把它配置成「不应包含 `data.skippy.io/storage`」：

```python
# core/scheduler.py
default_predicates = [
    PodFitsResourcesPred(),
    CheckNodeLabelPresencePred(['data.skippy.io/storage'], False),
]
```

## 7. 在调度器中的位置

```text
Scheduler.schedule(pod)
   ├─ list_nodes()
   ├─ 过滤：filter(node → passes_predicates(pod, node))
   │      └─ passes_predicates 内部按 default_predicates 逐项判定
   │             ├─ PodFitsResourcesPred
   │             └─ CheckNodeLabelPresencePred(['data.skippy.io/storage'], False)
   └─ 打分（只对过滤后的可行节点）
```

## 8. 跨模块依赖

| 引用来源 | 使用的成员 |
| --- | --- |
| `scheduler.py` | `PodFitsResourcesPred`, `CheckNodeLabelPresencePred` |
| `model.py` | `Pod`, `Node`, `Capacity`（仅类型注解） |
| `clustercontext.py` | `ClusterContext`（仅类型注解；谓词本身不读写上下文状态） |

## 9. 扩展点

新增一个谓词的最小代价：

```python
class MyNewPred(Predicate):
    def passes_predicate(self, context, pod, node) -> bool:
        # 自定义过滤逻辑
        return True
```

然后在 `Scheduler.__init__` 的 `predicates` 参数中替换或追加：

```python
Scheduler(cluster_context, predicates=[PodFitsResourcesPred(), MyNewPred()])
```
