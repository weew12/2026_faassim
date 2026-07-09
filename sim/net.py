"""
网络流安全包装。

SafeFlow 在 Ether flow 基础上增加低带宽检查，避免链路不可用或带宽过低时仿真静默继续，帮助尽早暴露拓扑或调度错误。
"""

import logging

from ether.core import Flow

logger = logging.getLogger(__name__)


class LowBandwidthException(BaseException):
    """
    链路带宽过低异常。

    SafeFlow 检测到不可接受带宽时抛出，防止网络仿真静默使用异常链路。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    pass


def SafeFlow(*args, bw_threshold=0.1, **kwargs):
    """
    创建安全网络流。

    当路由带宽不足或不存在时抛出 LowBandwidthException；正常情况下返回 ether 的 Flow 对象，用于模拟字节传输耗时。

    参数说明：
    - bw_threshold: 最小可接受带宽阈值，低于该值时认为链路不可用。
    - *args: 可变位置参数。
    - **kwargs: 可变关键字参数，通常用于透传指标标签或扩展配置。

    返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
    """
    flow = Flow(*args, **kwargs)

    bottleneck = min(flow.route.hops, key=lambda l: l.max_allocatable)

    if bottleneck.max_allocatable <= bw_threshold:
        logger.error('potential for flow %s: %.4f', flow.route, bottleneck.max_allocatable)
        raise LowBandwidthException()

    return flow
