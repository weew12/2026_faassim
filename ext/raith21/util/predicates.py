"""
Raith21 谓词集合装配工具。

本模块集中组合资源、可运行性、加速器及 GPU/TPU 独占谓词。
"""

from skippy.core.scheduler import Scheduler

from ext.raith21.predicates import CanRunPred, HasEnoughRamPredicate, NodeHasAcceleratorPred, NodeHasFreeGpu, \
    NodeHasFreeTpu


def get_predicates(fet_oracle, resource_oracle):
    """
    返回当前实验策略使用的 Skippy 谓词列表。

    参数:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 函数资源画像 Oracle。

    返回:
        内存、画像覆盖、加速器匹配及 GPU/TPU 可用性谓词列表。
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
