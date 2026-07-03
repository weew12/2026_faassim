"""Ether 预置网络单元文件，定义移动接入、企业 ISP、光纤回传、IoT 计算盒和 Cloudlet 等常见边缘网络结构。"""

import itertools
from collections import defaultdict

from ether.blocks.nodes import create_server_node
from ether.cell import LANCell, UpDownLink
from ether.qos import latency

# 按设备或网络单元类型维护的递增计数器，用于生成稳定唯一名称。
counters = defaultdict(lambda: itertools.count(0, 1))


class MobileConnection(UpDownLink):

    """移动网络回传配置，使用典型移动 ISP 上下行带宽和时延分布。"""
    def __init__(self, backhaul='internet') -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(125, 25, backhaul, latency.mobile_isp)


class BusinessIsp(UpDownLink):

    """企业网络回传配置，使用企业 ISP 上下行带宽和时延分布。"""
    def __init__(self, backhaul='internet') -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(500, 50, backhaul, latency.business_isp)


class FiberToExchange(UpDownLink):

    """光纤回传配置，使用对称高速带宽和局域网级时延。"""
    def __init__(self, backhaul='internet') -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        super().__init__(1000, 1000, backhaul, latency.lan)


class IoTComputeBox(LANCell):
    """IoT 计算盒网络单元，继承 LANCell，用于封装现场小型计算设备集合。"""
    pass


class Cloudlet(LANCell):
    """边缘 Cloudlet 单元，由若干机架和服务器组成，并通过回传链路接入上级网络。"""
    def __init__(self, server_per_rack=5, racks=1, backhaul=None) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - backhaul：上级网络、互联网骨干或回传链路配置。
        """
        # Cloudlet 中的机架数量。
        self.racks = racks
        # 每个机架中服务器节点数量。
        self.server_per_rack = server_per_rack

        # 该网络单元包含的子节点、子单元或节点工厂函数。
        nodes = [self._create_rack] * racks

        super().__init__(nodes, backhaul=backhaul)

    def _create_identity(self):
        """
        为网络单元生成唯一名称、编号和内部交换机/共享链路标识。

        """
        # 同类网络单元的递增编号，用于生成唯一名称。
        self.nr = next(counters['cloudlet'])
        # 业务名称或拓扑标识，用于日志、图顶点和调度标签引用。
        self.name = 'cloudlet_%d' % self.nr
        # LANCell 内部交换机标识，用作透明拓扑顶点。
        self.switch = 'switch_%s' % self.name

    def _create_rack(self):
        """
        内部辅助方法，服务于当前模块的主要业务流程。

        """
        return LANCell([create_server_node] * self.server_per_rack, backhaul=self.switch)
