"""
遗传算法调度策略装配工具。

本模块创建 Raith21 谓词集合，并按遗传算法给出的权重组合能力、争用和执行时间优先级。
"""

from ext.raith21.util import predicates
from ext.raith21.priorities import CapabilityMatchingPriority, ContentionPriority, ExecutionTimePriority


def get_predicates(fet_oracle, resource_oracle):
    """
    返回当前实验策略使用的 Skippy 谓词列表。

    参数:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 函数资源画像 Oracle。

    返回:
        Raith21 硬约束谓词列表。
    """
    return predicates.get_predicates(fet_oracle, resource_oracle)


def get_priorities(fet_oracle, resource_oracle, capability_weight: float = 1, contention_weight: float = 1,
                   fet_weight: float = 1):
    """
    返回当前实验策略使用的加权优先级列表。

    参数:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 函数资源画像 Oracle。
        capability_weight: 设备能力匹配优先级权重。 类型：float。
        contention_weight: 资源争用优先级权重。 类型：float。
        fet_weight: 预计执行时间优先级权重。 类型：float。

    返回:
        ``(权重, Priority)`` 三元策略列表，供 Skippy Scheduler 直接使用。
    """
    return [
        (capability_weight, CapabilityMatchingPriority()),
        (contention_weight, ContentionPriority(fet_oracle, resource_oracle)),
        (fet_weight, ExecutionTimePriority(fet_oracle))
    ]
