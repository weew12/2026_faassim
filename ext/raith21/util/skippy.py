"""
Skippy 基线策略装配工具。

本模块返回 Skippy 默认谓词和边缘感知优先级，并允许调整资源、镜像、位置、数据和能力权重。
"""

from skippy.core.priorities import DataLocalityPriority, LatencyAwareImageLocalityPriority, BalancedResourcePriority, \
    LocalityTypePriority, CapabilityPriority

from ext.raith21.util import predicates


def get_predicates(fet_oracle, resource_oracle):
    """
    返回当前实验策略使用的 Skippy 谓词列表。

    参数:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 函数资源画像 Oracle。

    返回:
        Skippy 默认硬约束谓词列表。
    """
    return predicates.get_predicates(fet_oracle, resource_oracle)


def get_priorities(balance_weight: float = 1, latency_weight: float = 1, locality_weight: float = 1,
                   data_weight: float = 1, cap_weight: float = 1):
    """
    返回当前实验策略使用的加权优先级列表。

    参数:
        balance_weight: 资源均衡优先级权重。 类型：float。
        latency_weight: 带宽感知镜像本地性权重。 类型：float。
        locality_weight: 边缘/云位置优先级权重。 类型：float。
        data_weight: 数据本地性优先级权重。 类型：float。
        cap_weight: 硬件能力匹配优先级权重。 类型：float。

    返回:
        ``(权重, Priority)`` 列表，供 Scheduler 加权打分。
    """
    return [
        (balance_weight, BalancedResourcePriority()),
        (latency_weight, DataLocalityPriority()),
        (data_weight, LatencyAwareImageLocalityPriority()),
        (locality_weight, LocalityTypePriority()),
        (cap_weight, CapabilityPriority())
    ]
