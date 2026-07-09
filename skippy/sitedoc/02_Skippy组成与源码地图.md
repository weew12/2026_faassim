# Skippy 组成与源码地图

## 包结构

```text
skippy/
  __init__.py
  core/
    __init__.py
    model.py
    clustercontext.py
    predicates.py
    priorities.py
    scheduler.py
    storage.py
    utils.py
```

faas-sim 侧的适配层在：

```text
sim/skippy.py
```

重点样例在：

```text
examples/03_skippy_scheduler/
```

## `model.py`：调度领域模型

`model.py` 定义调度器能理解的对象：

- `ImageState`
- `ResourceRequirements`
- `Container`
- `PodSpec`
- `Pod`
- `Capacity`
- `Node`
- `SchedulingResult`

它们是 Kubernetes 对象的简化版。Skippy 不直接使用 Kubernetes API，而是用这些纯 Python 对象表达调度所需信息。

## `clustercontext.py`：集群运行态上下文

`ClusterContext` 是调度器访问集群状态的统一接口。它负责提供：

- 节点列表；
- 镜像状态；
- 节点本地镜像缓存；
- 节点间带宽图；
- 对象存储索引；
- Pod 放置后的状态更新。

调度器通过它读取状态，也通过它写回调度结果。

## `predicates.py`：谓词过滤

谓词负责过滤不可行节点。

内置谓词包括：

- `PodFitsResourcesPred`：检查 CPU/内存是否足够；
- `CheckNodeLabelPresencePred`：检查节点标签是否存在或不存在；
- `CombinedPredicate`：组合多个谓词；
- `GeneralPreds`、`EssentialPreds`、`NonCriticalPreds`：Kubernetes 风格谓词集合。

默认调度器使用：

```python
default_predicates = [
    PodFitsResourcesPred(),
    CheckNodeLabelPresencePred(['data.skippy.io/storage'], False)
]
```

含义是：节点资源要够，并且普通函数不要调度到存储专用节点。

## `priorities.py`：优先级打分

优先级函数负责给可行节点打分。

默认优先级包括：

- `BalancedResourcePriority`
- `LatencyAwareImageLocalityPriority`
- `LocalityTypePriority`
- `DataLocalityPriority`
- `CapabilityPriority`

默认权重都是 `1.0`。调度器会把每个优先级函数的分数乘以权重再累加。

## `scheduler.py`：调度主流程

`Scheduler.schedule(pod)` 是 Skippy 最核心的方法。

它完成：

1. 获取候选节点；
2. 计算本轮最多需要找多少可行节点；
3. 执行谓词过滤；
4. 执行优先级函数打分；
5. 选择总分最高的节点；
6. 计算目标节点缺失的镜像；
7. 调用 `place_pod_on_node()` 写回上下文；
8. 返回 `SchedulingResult`。

## `storage.py`：对象存储索引

`StorageIndex` 用来描述数据对象在哪些存储节点上。

它不执行真实 I/O，只维护索引：

- bucket 在哪些节点上；
- object 属于哪个 bucket；
- object 大小；
- object 可从哪些节点读取。

`DataLocalityPriority` 会使用它估算数据读取和写回代价。

## `utils.py`：工具函数

常用工具包括：

- `normalize_image_name()`：给未带 tag 的镜像补 `:latest`；
- `parse_size_string()`：把 `103M`、`512Mi` 转成字节；
- `Timer`：简单计时；
- `counter()`：无限递增计数器。

## `sim/skippy.py`：faas-sim 适配层

`sim/skippy.py` 把 faas-sim 世界转换成 Skippy 世界：

- Ether Node -> Skippy Node；
- FunctionDeployment + FunctionContainer -> Pod；
- ContainerRegistry -> ImageState；
- Topology -> BandwidthGraph；
- StorageIndex -> Skippy 存储查询。

如果你想理解 Skippy 如何真正参与 faas-sim，必须读这个文件。

