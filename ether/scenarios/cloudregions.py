"""云区域场景文件，根据互联网延迟图中的云区域创建 Cloudlet，并把区域节点接入同一个拓扑。"""

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

        """
        for i in range(len(self.regions)):
            # 规模或大小字段：在 Flow 中表示待传输字节数，在 Cell/GeoCell 中表示需要生成的单元数量。
            size = self.region_size[i]
            Cloudlet(*size, backhaul=self.regions[i]).materialize(topology)
