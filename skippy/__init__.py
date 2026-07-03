"""内置 Skippy 调度子包。

本包由用户上传的 ``skippy-core`` 源码合入 faas-sim 项目根目录，用于替换原先通过
``edgerun-skippy-core`` 安装的外部依赖。faas-sim 中原有的导入方式保持不变，例如
``from skippy.core.scheduler import Scheduler``，因此调度器、谓词、优先级函数以及
集群上下文适配层无需改动调用方代码。

在 faas-sim 的业务流程中，Skippy 负责完成“函数副本 Pod 应该放到哪个节点”这一
核心决策。其输入是 faas-sim 适配出的 Pod、节点资源、镜像状态、带宽图和对象存储
位置；输出是建议节点、可行节点数量以及该节点还需要拉取的镜像列表。
"""

# 包名标识，保留原始 skippy-core 的公开变量，避免依赖该变量的外部代码失效。
name = 'skippy'
