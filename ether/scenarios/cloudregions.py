"""云区域场景文件，根据互联网延迟图中的云区域创建 Cloudlet，并把区域节点接入同一个拓扑。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【场景层】—— CloudRegionsScenario (多云区域场景)。

类: CloudRegionsScenario(regions, region_size)
    - regions: 云区域名列表, 如 ['us-east-1', 'eu-west-1', 'ap-southeast-1']
    - region_size: 每个区域的 Cloudlet 规模, 如 [(5, 2), (5, 2)]

    逻辑: 对每个 region 建一个 Cloudlet, backhaul = 区域名 (互联网图节点)
    关键: 必须先 load_inet_graph('cloudping') 才能让 backhaul 接到真实延迟

设计哲学:
    1. 跨大洲多区域调度场景
    2. 复用 blocks/cells.py 的 Cloudlet 工厂
    3. backhaul 直接是区域名 (字符串),由 inet 图注入延迟

对 CSAC 论文的接口:
    - 多区域调度实验 (跨大洲函数调用)
    - 自动接入真实 RTT 数据 (cloudping/gcloudping/wondernetwork)
================================================================================
"""

from typing import List, Tuple

from ether.blocks.cells import Cloudlet
from ether.topology import Topology


class CloudRegionsScenario:

    """多云区域拓扑场景，从互联网延迟图中选择云区域并创建对应 Cloudlet。"""
    def __init__(self, regions: List[str], region_size: List[Tuple[int, int]]) -> None:
        """
        初始化对象字段，把构造参数保存为后续拓扑构造、路由计算或流量仿真可直接读取的内部状态。
        """
        super().__init__()
        self.regions = regions
        self.region_size = region_size

    def materialize(self, topology: Topology):
        """
        把当前模板、网络单元或场景展开到给定 Topology 中。

        参数：
        - topology：需要写入节点、链路和连接的 Ether 拓扑图。

        ─────────────────────────────────────────────────────────────
        【设计意图】backhaul = 区域名的妙用
        ─────────────────────────────────────────────────────────────
        Cloudlet(*size, backhaul=self.regions[i]) 这里:
          - backhaul 不是 UpDownLink / Node 对象
          - 而是字符串 'us-east-1' 这样的区域名
        当 load_inet_graph('cloudping') 加载后,internet_us-east-1
        已经是图中的顶点,Cloudlet 的 backhaul 自动接上。
        这样场景不需要自己构造"区域间延迟",直接复用 cloudping 实测。
        ─────────────────────────────────────────────────────────────
        """
        for i in range(len(self.regions)):
            # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
            size = self.region_size[i]
            Cloudlet(*size, backhaul=self.regions[i]).materialize(topology)
