"""
文件作用：性能退化模型。

该模型用于描述节点并发请求数对函数执行时间的影响。
当同一节点上已有请求正在执行时，新请求的执行时间会被放大。
"""

from dataclasses import dataclass


@dataclass
class DegradationSample:
    """
    单次性能退化采样结果。
    """

    base_duration: float
    active_requests_before: int
    degradation_factor: float
    final_duration: float


class LinearNodeContentionDegradationModel:
    """
    线性节点竞争退化模型。

    模型形式：

    final_duration = base_duration * (1 + alpha * max(active_requests_before, 0))

    其中：
    - base_duration：无竞争时的基础执行时间；
    - active_requests_before：本请求加入前节点上正在执行的请求数量；
    - alpha：每个并发请求引入的执行时间放大系数。

    说明：
    本模型用于样例演示，强调机制可解释性。后续论文实验中可以替换为
    trace-driven、资源利用率驱动或节点类型感知的退化模型。
    """

    def __init__(self, base_duration: float = 0.4, alpha: float = 0.35):
        """
        初始化退化模型。
        """
        self.base_duration = base_duration
        self.alpha = alpha

    def sample(self, active_requests_before: int) -> DegradationSample:
        """
        根据当前节点并发请求数计算本次请求执行时间。
        """
        safe_active = max(int(active_requests_before), 0)
        factor = 1.0 + self.alpha * safe_active
        final_duration = self.base_duration * factor

        return DegradationSample(
            base_duration=self.base_duration,
            active_requests_before=safe_active,
            degradation_factor=factor,
            final_duration=final_duration,
        )
