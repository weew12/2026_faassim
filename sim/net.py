"""
文件作用：网络安全包装逻辑，在 Ether flow 基础上增加低带宽异常判断，避免资源受限链路被静默使用。
主要类：LowBandwidthException。
主要函数：SafeFlow。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import logging

from ether.core import Flow

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


class LowBandwidthException(BaseException):
    """
    类作用：LowBandwidthException 类，封装 low、bandwidth、exception 相关状态和业务操作。
    继承关系：BaseException。
    """
    pass


def SafeFlow(*args, bw_threshold=0.1, **kwargs):
    """
    函数作用：创建带低带宽保护的网络 flow，带宽过低时抛出异常。
    关键流程：
    - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：bw_threshold：表示 bw、threshold，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    flow = Flow(*args, **kwargs)

    bottleneck = min(flow.route.hops, key=lambda l: l.max_allocatable)

    if bottleneck.max_allocatable <= bw_threshold:
        logger.error('potential for flow %s: %.4f', flow.route, bottleneck.max_allocatable)
        raise LowBandwidthException()

    return flow
