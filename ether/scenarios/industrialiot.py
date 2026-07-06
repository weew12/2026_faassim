"""工业物联网场景文件，构造工厂现场 IoT 设备、边缘计算盒、企业网络和云端 Cloudlet 组成的拓扑。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【场景层】—— IndustrialIoTScenario (工业 IoT 场景)。

类: IndustrialIoTScenario(num_premises, premises_density, internet='internet')
    - num_premises: 工厂数量 (默认 1)
    - premises_density: 厂房内设备分布 (默认 ConstantSampler(10))

    每个工厂的典型结构:
        floor_compute = IoTComputeBox([NUC, TX2])         # 边缘计算设备
        floor_iot     = SharedLinkCell([RPI3] * 3)        # 3 个传感器共享带宽
        factory       = LANCell(以上, BusinessIsp)         # 厂内 LAN + 企业 ISP
        + cloudlet    = Cloudlet(5×3 server, 10G 光纤)    # 厂间云端聚合

设计哲学:
    1. 典型工业 IoT 三层架构: 传感器→边缘→云
    2. 混用 rpi3 / nuc / tx2 / server,异构性真实
    3. BusinessIsp + 10G 光纤,反映"厂内 + 厂间"两种链路

对 CSAC 论文的接口:
    - 工厂边缘计算 + 云端聚合场景
    - 模拟"厂内实时计算 + 厂间批量同步"
================================================================================
"""

from srds import ConstantSampler

from ether.blocks import nodes
from ether.blocks.cells import IoTComputeBox, Cloudlet, BusinessIsp
from ether.cell import LANCell, SharedLinkCell, UpDownLink
from ether.topology import Topology

# 城市感知场景默认小区数量。
default_num_cells = 1
# 城市小区感知节点数量的默认对数正态分布。
default_cell_density = ConstantSampler(10)


class IndustrialIoTScenario:
    """IndustrialIoTScenario 类负责封装当前模块中的业务状态和处理逻辑，是 Ether 网络拓扑/仿真流程的组成部分。"""
    def __init__(self, num_premises=default_num_cells, premises_density=default_cell_density,
                 internet='internet') -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - internet：场景连接到的互联网骨干节点或延迟图标识。
        """
        super().__init__()
        self.num_premises = num_premises
        self.premises_density = premises_density
        # 场景接入的互联网骨干或云区域延迟图节点名称。
        self.internet = internet

    def materialize(self, topology: Topology):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。

        ─────────────────────────────────────────────────────────────
        【设计意图】为什么 Cloudlet backhaul 用 10G 对称光纤?
        ─────────────────────────────────────────────────────────────
        UpDownLink(10000, 10000, backhaul=factory.switch) 表示:
          - 下行 10G, 上行 10G (对称,符合机房内部高速链路)
          - backhaul 是 factory.switch (厂内 LAN 的交换机)
        把"厂间云端"接在"厂内 LAN 交换机"上,
        模拟"工厂内网有高速通道直达云端"。

        对比: 厂内传感器共享 WiFi (SharedLinkCell),
              厂间云端走 10G 光纤
        异构链路 + 异构设备 = 真实工业 IoT 部署
        ─────────────────────────────────────────────────────────────
        """
        for _ in range(self.num_premises):
            floor_compute = IoTComputeBox(nodes=[nodes.nuc, nodes.tx2])
            floor_iot = SharedLinkCell(nodes=[nodes.rpi3] * 3)

            factory = LANCell([floor_compute, floor_iot], backhaul=BusinessIsp(self.internet))
            factory.materialize(topology)

            cloudlet = Cloudlet(5, 3, backhaul=UpDownLink(10000, 10000, backhaul=factory.switch))
            cloudlet.materialize(topology)
