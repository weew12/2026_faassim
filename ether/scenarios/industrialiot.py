"""工业物联网场景文件，构造工厂现场 IoT 设备、边缘计算盒、企业网络和云端 Cloudlet 组成的拓扑。"""

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

        """
        for _ in range(self.num_premises):
            floor_compute = IoTComputeBox(nodes=[nodes.nuc, nodes.tx2])
            floor_iot = SharedLinkCell(nodes=[nodes.rpi3] * 3)

            factory = LANCell([floor_compute, floor_iot], backhaul=BusinessIsp(self.internet))
            factory.materialize(topology)

            cloudlet = Cloudlet(5, 3, backhaul=UpDownLink(10000, 10000, backhaul=factory.switch))
            cloudlet.materialize(topology)
