# skippy 包结构说明

`skippy/` 是本版本内置的调度器子包，用于替换原先的 `edgerun-skippy-core` 外部依赖。它提供 Kubernetes 风格的调度模型，将函数副本抽象为 Pod，将边缘/云节点抽象为 Node，并通过“谓词过滤 + 优先级打分”的流程选择部署节点。

## 目录结构

```text
skippy/
├── __init__.py
└── core/
    ├── __init__.py
    ├── model.py
    ├── clustercontext.py
    ├── predicates.py
    ├── priorities.py
    ├── scheduler.py
    ├── storage.py
    └── utils.py
```

## 文件职责

- `model.py`：定义调度领域对象，包括 `ImageState`、`ResourceRequirements`、`Container`、`PodSpec`、`Pod`、`Capacity`、`Node` 和 `SchedulingResult`。
- `clustercontext.py`：定义集群运行态上下文，维护节点、镜像、剩余资源、带宽图和对象存储索引。
- `predicates.py`：定义调度过滤逻辑，例如资源是否足够、节点是否带有或不带有指定标签。
- `priorities.py`：定义调度打分逻辑，例如资源均衡、镜像本地性、带宽感知镜像拉取代价、数据本地性、边缘节点优先和硬件能力匹配。
- `scheduler.py`：串联过滤和打分流程，选择最高分节点，并将调度结果写回 `ClusterContext`。
- `storage.py`：维护对象存储 bucket、数据对象和存储节点之间的索引关系，供数据本地性调度使用。
- `utils.py`：提供镜像名规范化、容量字符串解析、计时器和递增计数器等工具。

## 核心业务流程

1. faas-sim 通过 `sim/skippy.py` 将 Ether 节点转换为 Skippy `Node`，将函数部署转换为 Skippy `Pod`。
2. `Scheduler.schedule(pod)` 从 `ClusterContext` 获取节点列表。
3. 调度器执行默认谓词：资源必须足够，且普通函数不能被放到存储专用节点。
4. 对可行节点执行默认优先级函数：资源均衡、镜像拉取代价、边缘位置、数据本地性和能力匹配。
5. 调度器选择总分最高节点，并计算该节点缺失的镜像列表。
6. 调度器调用 `ClusterContext.place_pod_on_node()`，扣减节点剩余资源并登记镜像缓存状态。
7. faas-sim 根据调度结果继续模拟镜像拉取、函数启动、setup 和请求执行。
