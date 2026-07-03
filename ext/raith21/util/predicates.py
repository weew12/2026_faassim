"""
文件作用：源码模块，包含 0 个类和 1 个顶层函数，承担 predicates 相关的仿真支撑逻辑。
主要函数：get_predicates。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from skippy.core.scheduler import Scheduler

from ext.raith21.predicates import CanRunPred, HasEnoughRamPredicate, NodeHasAcceleratorPred, NodeHasFreeGpu, \
    NodeHasFreeTpu


def get_predicates(fet_oracle, resource_oracle):
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    predicates = []
    predicates.extend(Scheduler.default_predicates)
    predicates.extend([
        CanRunPred(fet_oracle, resource_oracle),
        HasEnoughRamPredicate(resource_oracle),
        NodeHasAcceleratorPred(),
        NodeHasFreeGpu(),
        NodeHasFreeTpu()
    ])
    return predicates
