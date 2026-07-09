# Skippy 中文文档导航

这组文档面向源码阅读者和 faas-sim 使用者，目标是把 Skippy 从“是什么”讲到“如何读源码、如何运行、如何扩展”。文档基于本仓库内置源码：

- `skippy/core/model.py`
- `skippy/core/clustercontext.py`
- `skippy/core/predicates.py`
- `skippy/core/priorities.py`
- `skippy/core/scheduler.py`
- `skippy/core/storage.py`
- `skippy/core/utils.py`
- `sim/skippy.py`
- `examples/03_skippy_scheduler/`

## 推荐阅读顺序

1. [01_Skippy总体介绍_概念与定位.md](01_Skippy总体介绍_概念与定位.md)
2. [02_Skippy组成与源码地图.md](02_Skippy组成与源码地图.md)
3. [03_核心对象模型_Node_Pod_Container.md](03_核心对象模型_Node_Pod_Container.md)
4. [04_调度主流程_过滤_打分_绑定.md](04_调度主流程_过滤_打分_绑定.md)
5. [05_谓词过滤与优先级打分.md](05_谓词过滤与优先级打分.md)
6. [06_faas-sim中的Skippy适配层.md](06_faas-sim中的Skippy适配层.md)
7. [07_入门案例_从最小调度到03样例.md](07_入门案例_从最小调度到03样例.md)
8. [08_扩展开发与源码阅读路线.md](08_扩展开发与源码阅读路线.md)

## 一句话理解 Skippy

Skippy 是 faas-sim 中的 Kubernetes 风格调度器：它把函数副本表示成 Pod，把边缘/云节点表示成 Node，然后通过“谓词过滤 + 优先级打分”决定每个函数副本应该放到哪个节点。

## 文档覆盖范围

这组文档覆盖：

- Skippy 的调度目标和适用场景；
- Node、Pod、Container、ImageState、StorageIndex 等核心模型；
- ClusterContext 如何保存集群运行态；
- Scheduler 的过滤、打分、选点、状态写回流程；
- 默认谓词和默认优先级函数；
- Skippy 如何接入 faas-sim 的 Environment、Topology、ContainerRegistry；
- 最小可运行调度案例；
- `examples/03_skippy_scheduler` 的样例结构和输出；
- 如何扩展谓词、优先级函数、ClusterContext 和 Scheduler。

