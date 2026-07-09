# Skippy 总体介绍：概念与定位

## Skippy 是什么

Skippy 是一个面向 serverless edge computing 的调度器。在本仓库中，它以内置 Python 包 `skippy/` 的形式存在，不依赖真实 Kubernetes API，而是用轻量对象模拟 Kubernetes 调度器需要的关键状态。

它解决的问题是：

> 当一个函数副本要启动时，应该把它放到哪个边缘节点、云节点或异构节点上？

这个选择不仅取决于 CPU 和内存是否够，还取决于：

- 节点是否已有目标容器镜像；
- 镜像从 registry 拉到节点要多久；
- 输入数据在哪里；
- 输出数据要写回哪里；
- 节点是 edge 还是 cloud；
- 节点是否具备函数需要的硬件能力；
- 当前节点剩余资源是否会导致资源失衡。

## Skippy 在 faas-sim 中的位置

faas-sim 的整体流程可以简化成：

```text
Benchmark 创建函数部署
    |
DefaultFaasSystem.scale_up()
    |
create_function_pod()
    |
Skippy Scheduler.schedule(pod)
    |
SchedulingResult.suggested_host
    |
simulate_function_start()
```

其中 Skippy 只负责“选择节点”。它不会真正启动容器，也不会直接模拟函数执行。容器启动、镜像拉取、函数执行、网络传输由 faas-sim 的生命周期模拟器继续处理。

## Skippy 和 Kubernetes 调度器的关系

Skippy 借鉴 Kubernetes 默认调度器的结构：

```text
待调度 Pod
  -> 谓词过滤 Predicates
  -> 优先级打分 Priorities
  -> 选择最高分节点
  -> 写回调度状态
```

两者的区别是：

- Kubernetes 面向真实集群；
- 本仓库的 Skippy 面向仿真；
- Skippy 增加了边缘场景需要的数据本地性、镜像本地性、带宽、存储索引、节点位置和硬件能力信息。

## Skippy 的核心思想

Skippy 的核心思想是把调度问题拆成两个阶段。

第一阶段：过滤。

过滤阶段回答：

> 这个 Pod 能不能放到这个节点上？

例如：

- 节点 CPU 是否足够；
- 节点内存是否足够；
- 普通函数是否不应该放到存储专用节点。

第二阶段：打分。

打分阶段回答：

> 在所有可行节点里，哪个节点更适合？

例如：

- 放到这个节点后 CPU 和内存是否更均衡；
- 这个节点是否已经缓存镜像；
- 从 registry 到这个节点拉镜像是否更快；
- 这个节点是否更靠近输入数据；
- 这个节点是否是 edge；
- 这个节点是否满足 GPU/TPU 等能力偏好。

## 什么时候需要理解 Skippy

如果你只是运行已有样例，知道 Skippy 是默认调度器即可。

如果你要做以下事情，就需要理解 Skippy 源码：

- 设计新的调度策略；
- 修改函数副本放置逻辑；
- 做数据本地性、镜像缓存、边缘节点选择实验；
- 分析为什么某个 Pod 被调度到某个节点；
- 解释 `schedule.csv`、`skippy_scheduler_result.csv` 等输出；
- 扩展 faas-sim 的调度器或实验 benchmark。

## 本仓库中的 Skippy 与原始 skippy-core

本仓库把 Skippy 源码内置在 `skippy/` 目录下。这样代码可以直接通过以下路径导入：

```python
from skippy.core.scheduler import Scheduler
from skippy.core.model import Pod, Node, SchedulingResult
```

`setup.py` 中也说明了 `skippy/ether/simpy` 这类内置子包会被 `setuptools.find_packages()` 自动发现。

