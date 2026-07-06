# skippy 包结构说明（精简入口）

> 本文档是**精简入口**。完整导航与各模块深度解析请见 [doc/](doc/)。
>
> 本包的目的、目录结构、文件职责与核心业务流程的**完整说明**已拆分到以下子文档：
>
> - [00 · 包结构与导航](doc/00_包结构与导航.md) — 总览（推荐从这里开始）
> - [01 · 包入口与 core 子包](doc/01_包入口与core子包.md) — 两个 __init__.py
> - [02 · 调度领域模型](doc/02_调度领域模型_model.md) — core/model.py
> - [03 · 集群运行态上下文](doc/03_集群运行态上下文_clustercontext.md) — core/clustercontext.py
> - [04 · 调度谓词过滤](doc/04_调度谓词过滤_predicates.md) — core/predicates.py
> - [05 · 调度优先级打分](doc/05_调度优先级打分_priorities.md) — core/priorities.py
> - [06 · 调度器主流程](doc/06_调度器主流程_scheduler.md) — core/scheduler.py
> - [07 · 对象存储索引](doc/07_对象存储索引_storage.md) — core/storage.py
> - [08 · 调度工具函数](doc/08_调度工具函数_utils.md) — core/utils.py
>
> 本文件保留作为从仓库根目录快速进入的入口指引，**避免与 doc/00_包结构与导航.md 重复维护**。

---

## 一句话总览

skippy/ 是 faas-sim 内置的调度器子包（替换原 dgerun-skippy-core），通过 **Kubernetes 风格的「谓词过滤 + 优先级打分」** 决定「函数副本 Pod 应该放到哪个边缘/云节点」。
