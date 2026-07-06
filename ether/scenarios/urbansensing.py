"""城市感知场景文件，参考 Array of Things 思路生成城市小区、感知节点、近端计算资源和 Cloudlet。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【场景层】—— UrbanSensingScenario (城市感知场景)。

类: UrbanSensingScenario(num_cells, cell_density, cloudlet_size, internet='internet')
    - num_cells: 城区数量 (默认 3)
    - cell_density: 每个城区的节点数分布 (默认 lognorm((0.82, 2.02)))
    - cloudlet_size: Cloudlet 规模 (默认 (5, 2) = 5×2 server)

    场景分两部分:
      1) create_city():    GeoCell 生成 num_cells 个城区
                          每个城区是 SharedLinkCell(500M, MobileConnection)
                          城区节点数从 cell_density.sample() 采样
      2) create_cloudlet(): 城市级 Cloudlet(FiberToExchange 上联)

设计哲学:
    1. Array of Things 思路: 每个城市角落布 RPI3 传感器
    2. GeoCell + 真实分布: 城区节点数从对数正态采样,贴近现实
    3. 移动回传: MobileConnection (125/25 Mbit/s, mobile_isp 时延)
    4. lambda size: 工厂接收 GeoCell 注入的 density.sample() 值
       → 近端计算资源(NUC + 2N TX2)跟节点数成比例

对 CSAC 论文的接口:
    - 城市级边缘部署 (规模可调)
    - 移动回传场景 (5G/4G)
    - 非固定节点数 (从分布采样)
================================================================================
"""

from srds import ParameterizedDistribution

from ether.blocks import nodes
from ether.blocks.cells import Cloudlet, IoTComputeBox, MobileConnection, FiberToExchange
from ether.cell import GeoCell, SharedLinkCell
from ether.topology import Topology

# 城市感知场景默认小区数量。
default_num_cells = 3
# 城市感知场景默认 Cloudlet 规模。
default_cloudlet_size = (5, 2)
# 城市小区感知节点数量的默认对数正态分布。
default_cell_density = ParameterizedDistribution.lognorm((0.82, 2.02))


class UrbanSensingScenario:
    """城市感知拓扑场景，生成多个城区单元以及一个城市级 Cloudlet。"""
    def __init__(self, num_cells=default_num_cells, cell_density=default_cell_density,
                 cloudlet_size=default_cloudlet_size, internet='internet') -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。

        参数：
        - num_cells：需要生成的地理小区数量。
        - cell_density：每个城市小区中的感知节点数量分布。
        - cloudlet_size：Cloudlet 规模，通常为每机架服务器数和机架数。
        - internet：场景连接到的互联网骨干节点或延迟图标识。
        """
        super().__init__()
        # 城市或地理场景中需要生成的区域/小区数量。
        self.num_cells = num_cells
        # 城市每个小区内感知节点数量的分布。
        self.cell_density = cell_density
        # Cloudlet 规模参数，通常为每机架服务器数和机架数。
        self.cloudlet_size = cloudlet_size
        # 场景接入的互联网骨干或云区域延迟图节点名称。
        self.internet = internet

    def materialize(self, topology: Topology):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。

        ─────────────────────────────────────────────────────────────
        【设计意图】create_city + create_cloudlet 分两步物化
        ─────────────────────────────────────────────────────────────
        分成两个方法:
          1) create_city()    → GeoCell, 城市级重复
          2) create_cloudlet() → Cloudlet, 城市级聚合资源
        然后 materialize 调 topology.add(self.create_city()) + add(create_cloudlet)

        好处:
          - 用户可以单独用 create_city() 或 create_cloudlet()
          - 也可以扩展类,重写其中一个方法做自定义
        ─────────────────────────────────────────────────────────────
        """
        topology.add(self.create_city())
        topology.add(self.create_cloudlet())

    def create_city(self) -> GeoCell:
        """
        构造城市感知场景中的城区单元，包含感知节点、近端计算盒和移动回传链路。

        ─────────────────────────────────────────────────────────────
        【设计意图】lambda size: SharedLinkCell(...) 的妙用
        ─────────────────────────────────────────────────────────────
        neighborhood = lambda size: SharedLinkCell(
            nodes=[
                [aot_node] * size,                                # N 个 AOT
                IoTComputeBox([nodes.nuc] + ([nodes.tx2] * size * 2))  # 1 NUC + 2N TX2
            ],
            ...
        )
        size 由 GeoCell 注入 (来自 density.sample() 的返回值)。
        inspect.signature 检测到 len(parameters) > 0 → 调 c(n) 而不是 c()。

        实际效果: 每个城区的 AOT 数 = size, TX2 数 = 2 * size
                  → 近端计算资源跟传感器数成比例
                  → 符合"每 N 个传感器配 1 个 NUC + 2N 个 TX2"工程经验
        ─────────────────────────────────────────────────────────────
        """
        aot_node = IoTComputeBox(nodes=[nodes.rpi3, nodes.rpi3])

        neighborhood = lambda size: SharedLinkCell(
            nodes=[
                [aot_node] * size,
                IoTComputeBox([nodes.nuc] + ([nodes.tx2] * size * 2))
            ],
            shared_bandwidth=500,
            backhaul=MobileConnection(self.internet)
        )

        city = GeoCell(self.num_cells, nodes=[neighborhood], density=self.cell_density)

        return city

    def create_cloudlet(self) -> Cloudlet:
        """
        构造场景中的 Cloudlet 计算资源，并通过指定回传链路接入互联网或上级网络。

        """
        return Cloudlet(*self.cloudlet_size, backhaul=FiberToExchange(self.internet))
