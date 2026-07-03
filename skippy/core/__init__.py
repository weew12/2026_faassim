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
