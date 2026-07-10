"""
Kubernetes 风格基线策略装配工具。

本模块返回基础资源谓词和等价基线优先级，用于与 Skippy 及 Raith21 workload-aware 策略对比。
"""

from skippy.core.priorities import ImageLocalityPriority, BalancedResourcePriority

from ext.raith21.util import predicates


def get_predicates(fet_oracle, resource_oracle):
    """
    返回当前实验策略使用的 Skippy 谓词列表。

    参数:
        fet_oracle: 函数执行时间 Oracle。
        resource_oracle: 函数资源画像 Oracle。

    返回:
        Kubernetes 风格基础资源谓词列表。
    """
    return predicates.get_predicates(fet_oracle, resource_oracle)


def get_priorities():
    """
    返回当前实验策略使用的加权优先级列表。

    返回:
        vanilla 基线优先级列表。
    """
    return [
        (1, BalancedResourcePriority()),
        (1, ImageLocalityPriority()),
    ]
