# 01 · 包入口与 core 子包

> 解析文件：`skippy/__init__.py`、`skippy/core/__init__.py`
>
> 这两份 `__init__.py` **不承载业务逻辑**，主要做包级元信息声明和子包结构总览。它们的存在有两个作用：
>
> 1. 保留外部代码可能依赖的 `name` 变量，使得从 `edgerun-skippy-core` 切到内置包后无须修改调用方；
> 2. 在 `core/__init__.py` 中以文档字符串的形式给读者一份「读源码前的目录地图」。

## 1. `skippy/__init__.py`

### 1.1 文件职责

- 作为 `skippy` 包的入口标识；
- 在模块 docstring 中**说明本包替换 `edgerun-skippy-core` 的事实**，并列出 faas-sim 仍然按 `from skippy.core.scheduler import Scheduler` 这类路径导入；
- 声明公共变量 `name = 'skippy'`，保留原始 `skippy-core` 的对外标识。

### 1.2 关键内容

```python
"""内置 Skippy 调度子包。

本包由用户上传的 ``skippy-core`` 源码合入 faas-sim 项目根目录，用于替换原先通过
``edgerun-skippy-core`` 安装的外部依赖。faas-sim 中原有的导入方式保持不变，例如
``from skippy.core.scheduler import Scheduler``，因此调度器、谓词、优先级函数以及
集群上下文适配层无需改动调用方代码。

在 faas-sim 的业务流程中，Skippy 负责完成"函数副本 Pod 应该放到哪个节点"这一
核心决策。其输入是 faas-sim 适配出的 Pod、节点资源、镜像状态、带宽图和对象存储
位置；输出是建议节点、可行节点数量以及该节点还需要拉取的镜像列表。
"""

# 包名标识，保留原始 skippy-core 的公开变量，避免依赖该变量的外部代码失效。
name = 'skippy'
```

### 1.3 设计要点

| 要点 | 说明 |
| --- | --- |
| `name` 变量 | 保留与原始 skippy-core 一致的对外标识；外部若按 `skippy.__name__` 或 `skippy.name` 取包名，迁移后仍可工作。 |
| docstring | 起到「自描述入口」的作用，IDE/PyDoc 工具直接显示该说明，无需再翻 README。 |
| 不再 `from .core import ...` | 入口不主动 re-export 模块，避免 `from skippy import Scheduler` 与 `from skippy.core import Scheduler` 两种风格并存造成歧义。 |

## 2. `skippy/core/__init__.py`

### 2.1 文件职责

- 作为 `core` 子包的入口标识；
- 在模块 docstring 中**列出 core 子包内每个文件的作用**，并给出与 faas-sim 的衔接关系（`sim/skippy.py`）；
- 声明公共变量 `name = 'core'`，保留原始 skippy-core 的对外标识。

### 2.2 关键内容

```python
"""Skippy 核心调度模型包。

该目录封装了一个接近 Kubernetes 调度器思想的轻量实现，主要由以下部分组成：

1. ``model.py``：定义 Node、Pod、Container、Capacity、SchedulingResult 等调度对象；
2. ``clustercontext.py``：维护集群运行态，包括节点列表、剩余资源、镜像分布、带宽图和存储索引；
3. ``predicates.py``：实现过滤阶段，用于判断某个 Pod 是否能放到某个节点；
4. ``priorities.py``：实现打分阶段，用于对可行节点按资源均衡、镜像本地性、数据本地性等因素评分；
5. ``scheduler.py``：串联过滤与打分流程，产生最终调度结果；
6. ``storage.py`` 和 ``utils.py``：提供对象存储索引、镜像名规范化、容量字符串解析等基础工具。

faas-sim 通过 ``sim/skippy.py`` 将 Ether 拓扑节点和 FunctionDeployment 转换为这里的
Node/Pod 视图，从而复用 Skippy 的调度逻辑。
"""

# 包名标识，保留原始 skippy-core 的公开变量。
name = 'core'
```

### 2.3 设计要点

| 要点 | 说明 |
| --- | --- |
| 子包结构地图 | 在 docstring 里列出 6 个核心模块的作用，是新人最快的入手点。 |
| 与 faas-sim 的边界 | 明确「`sim/skippy.py` 负责适配，core 只关心调度」，避免后续改动时职责越界。 |
| `name = 'core'` | 同样为兼容旧代码而保留的标识符。 |

## 3. 与其他子文档的关系

本子文档只是「包级骨架」，具体业务逻辑在以下子文档中：

- 调度领域对象 → [02_调度领域模型_model.md](02_调度领域模型_model.md)
- 集群运行态 → [03_集群运行态上下文_clustercontext.md](03_集群运行态上下文_clustercontext.md)
- 过滤与打分逻辑 → [04_调度谓词过滤_predicates.md](04_调度谓词过滤_predicates.md) / [05_调度优先级打分_priorities.md](05_调度优先级打分_priorities.md)
- 主流程串联 → [06_调度器主流程_scheduler.md](06_调度器主流程_scheduler.md)
- 底层支撑（存储索引、工具函数）→ [07_对象存储索引_storage.md](07_对象存储索引_storage.md) / [08_调度工具函数_utils.md](08_调度工具函数_utils.md)
