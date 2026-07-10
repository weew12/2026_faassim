"""
Raith21 异构边缘拓扑构造器。

本模块把 Xeon、Raspberry Pi、Jetson、Coral、NUC 等节点组织为云、cloudlet、接入点和移动网络拓扑，并同步建立存储索引。
"""

import logging
import random
from typing import List

from ether.blocks.cells import FiberToExchange, IoTComputeBox
from ether.cell import LANCell, GeoCell, counters, SharedLinkCell, UpDownLink
from ether.core import Node
from ether.scenarios.urbansensing import UrbanSensingScenario, default_cell_density, default_num_cells, \
    default_cloudlet_size
from skippy.core.storage import StorageIndex
from srds import IntegerTruncationSampler

from ext.raith21 import storage
from sim.topology import Topology

logger = logging.getLogger(__name__)


def all_internet_topology(nodes: List[Node]) -> Topology:
    """
    创建所有计算节点都直接连接互联网的简单拓扑。

    每个节点被放入独立 LANCell，并通过 internet 回程连接；该拓扑用于隔离复杂城市网络
    结构的影响，适合作为调度和设备能力实验的简单基线。

    参数:
        nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。

    返回:
        Topology。
    """
    t = Topology()
    for node in nodes:
        cell = LANCell(nodes=[node], backhaul='internet')
        t.add(cell)
    t.init_docker_registry()

    return t


def urban_sensing_topology(nodes: List[Node], storage_index: StorageIndex) -> Topology:
    """
    创建 Raith21 异构城市感知拓扑。

    HeterogeneousUrbanSensingScenario 会按节点类型构造 cloudlet、接入点、移动链路和存储
    位置；完成物化后再接入 Docker registry。

    参数:
        nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。
        storage_index: 对象存储位置索引。 类型：StorageIndex。

    返回:
        Topology。
    """
    t = Topology()
    HeterogeneousUrbanSensingScenario(nodes, storage_index).materialize(t)
    t.init_docker_registry()

    return t


class XeonCloudlet(LANCell):

    """
    Xeon cloudlet 拓扑组件。

    创建一组 Xeon 节点并通过交换机连接，表示边缘侧小型服务器集群。

    关键字段:
        name: 拓扑组件名称。
        xeons: cloudlet 中的 Xeon 节点列表。
        xeon_vms_per_rack: 每个机架容纳的 Xeon 节点数。
        racks: 根据节点数量计算的机架数。
    """
    def __init__(self, xeons: List[Node], xeon_vms_per_rack=5, backhaul=None):
        """
        初始化 XeonCloudlet。

        建立字段：name、xeons、xeon_vms_per_rack、racks。

        参数:
            xeons: Xeon 节点列表。 类型：List[Node]。
            xeon_vms_per_rack: 每个机架的 Xeon 节点数。
            backhaul: 上联网络或回程链路。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.name = None
        self._create_identity()
        self.xeons = xeons
        self.xeon_vms_per_rack = xeon_vms_per_rack
        self.racks = int(len(self.xeons) / self.xeon_vms_per_rack)
        nodes = self.create_nodes()

        super().__init__(nodes, backhaul=backhaul)

    def create_nodes(self) -> List[LANCell]:
        """
        按 xeon_vms_per_rack 把 Xeon 节点拆成多个机架 LANCell。

        每个机架都连接到 cloudlet switch；最后不足一个完整机架的节点仍会形成独立 LANCell。

        返回:
            List[LANCell]。
        """
        nodes = []
        rack = []
        for node in self.xeons:
            rack.append(node)
            if len(rack) == self.xeon_vms_per_rack:
                cell = LANCell(rack, backhaul=self.switch)
                nodes.append(cell)
                rack = []
        if len(rack) > 0:
            cell = LANCell(rack, backhaul=self.switch)
            nodes.append(cell)
        return nodes

    def _create_identity(self):
        """
        为 cloudlet 分配递增编号、名称和交换机名称。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        if self.name is None:
            self.nr = next(counters['cloudlet'])
            self.name = 'cloudlet_%d' % self.nr
            self.switch = 'switch_%s' % self.name


def parts(a, b):
    """
    尽量均匀地把整数 a 分成 b 份。

    前 a % b 份比其余分组多 1，用于给不同加速器类型分配节点数量。

    参数:
        a: 需要被均分的总数。
        b: 分组数量。

    返回:
        计算、查询或构造得到的结果。
    """
    q, r = divmod(a, b)
    return [q + 1] * r + [q] * (b - r)


class FasterMobileConnection(UpDownLink):

    """
    高速移动网络连接模型。

    在 Ether 移动连接模型基础上使用 Raith21 实验设定的回程链路参数。
    """
    def __init__(self, backhaul='internet') -> None:
        """
        初始化 FasterMobileConnection。

        参数:
            backhaul: 上联网络或回程链路。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        super().__init__(250, 250, backhaul)


class HeterogeneousUrbanSensingScenario(UrbanSensingScenario):

    """
    异构城市感知拓扑场景。

    按设备类型分组输入节点，并把云、cloudlet、接入点、移动设备和存储节点组织成完整 Ether 拓扑。

    关键字段:
        nodes: 场景使用的节点集合。
        storage_index: 对象数据位置索引。
        xeon_nodes: Xeon 节点集合。
        rpi3_nodes: Raspberry Pi 3 节点集合。
        rpi4_nodes: Raspberry Pi 4 节点集合。
        rockpi_nodes: RockPi 节点集合。
        tx2_nodes: Jetson TX2 节点集合。
        nx_nodes: Jetson Xavier NX 节点集合。
        nano_nodes: Jetson Nano 节点集合。
        coral_nodes: Coral TPU 节点集合。
        nuc_nodes: Intel NUC 节点集合。
    """
    def __init__(self, nodes: List[Node], storage_index: StorageIndex, num_cells=default_num_cells,
                 cell_density=default_cell_density,
                 cloudlet_size=default_cloudlet_size, internet='internet') -> None:
        """
        初始化 HeterogeneousUrbanSensingScenario。

        建立字段：nodes、storage_index、xeon_nodes、rpi3_nodes、rpi4_nodes、rockpi_nodes、tx2_nodes、nx_nodes、nano_nodes、coral_nodes、nuc_nodes。

        参数:
            nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。
            storage_index: 对象存储位置索引。 类型：StorageIndex。
            num_cells: 城市拓扑中的 cell 数量。
            cell_density: 每个 cell 的节点密度采样配置。
            cloudlet_size: cloudlet 节点规模。
            internet: 互联网回程节点名称。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.nodes = nodes
        self.storage_index = storage_index
        self.xeon_nodes = self._get_xeon_nodes()
        self.rpi3_nodes = self._get_rpi3_nodes()
        self.rpi4_nodes = self._get_rpi4_nodes()
        self.rockpi_nodes = self._get_rockpi_nodes()
        self.tx2_nodes = self._get_tx2_nodes()
        self.nx_nodes = self._get_nx_nodes()
        self.nano_nodes = self._get_nano_nodes()
        self.coral_nodes = self._get_coral_nodes()
        self.nuc_nodes = self._get_nuc_nodes()

        super().__init__(num_cells, cell_density, cloudlet_size, internet)

    def create_city(self) -> GeoCell:
        """
        构造异构城市感知网络拓扑。

        返回:
            GeoCell。
        """
        # AOT 节点是接入点附近的普通 SBC，随后会按 cell density 分配到多个 neighborhood。
        aot_nodes = []
        aot_nodes.extend(self.create_rpi3_aot_nodes())
        aot_nodes.extend(self.create_rpi4_aot_nodes())
        aot_nodes.extend(self.create_rockpi_aot_nodes())
        nx_nodes = self.nx_nodes
        tx2_nodes = self.tx2_nodes
        nano_nodes = self.nano_nodes
        coral_nodes = self.coral_nodes
        nuc_nodes = self.nuc_nodes
        random.shuffle(aot_nodes)
        neighborhoods = []
        sampler = IntegerTruncationSampler(self.cell_density)
        while len(aot_nodes) > 0:
            size = sampler.sample()

            if size < 4:
                take = random.randint(0, size - 1)
                if take == 0:
                    take = 1
                split = parts(size, take)
            else:
                take = size % 5
                if take == 0:
                    take = 1
                split = parts(size, take)

            while len(split) != 4:
                split.append(0)
            random.shuffle(split)
            choices = random.choices(['tx2', 'nano', 'coral', 'nx'], weights=split, k=take)

            def select_nodes(nodes, n):
                """从节点列表头部取最多 n 个节点，并返回剩余节点与已选节点。"""
                if n > len(nodes):
                    diff = n - len(nodes)
                    n -= diff
                return nodes[selected_size:], nodes[:selected_size]

            # 按前面生成的 split，把 TX2/NX/Nano/Coral 加速节点分配到当前 neighborhood。
            selected_accelerator_nodes = []
            for i in range(take):
                node = choices[i]
                selected_size = split[i]
                if node == 'tx2':
                    tx2_nodes, selected_nodes = select_nodes(tx2_nodes, selected_size)
                    selected_accelerator_nodes.extend(selected_nodes)
                elif node == 'nx':
                    nx_nodes, selected_nodes = select_nodes(nx_nodes, selected_size)
                    selected_accelerator_nodes.extend(selected_nodes)
                elif node == 'nano':
                    nano_nodes, selected_nodes = select_nodes(nano_nodes, selected_size)
                    selected_accelerator_nodes.extend(selected_nodes)
                elif node == 'coral':
                    coral_nodes, selected_nodes = select_nodes(coral_nodes, selected_size)
                    selected_accelerator_nodes.extend(selected_nodes)

            selected_nuc_nodes = []

            if len(nuc_nodes) > 0:
                selected_nuc_nodes.append(nuc_nodes[0])
                nuc_nodes = nuc_nodes[1:]

            selected_aot_nodes = []
            if len(aot_nodes) > 0:
                if size > len(aot_nodes):
                    diff = size - len(aot_nodes)
                    size -= diff

                selected_aot_nodes = aot_nodes[:size]
                aot_nodes = aot_nodes[size:]
            # 加速节点通过 IoTComputeBox 聚合；普通 SBC 与可选 NUC 共享当前接入链路。
            if len(selected_accelerator_nodes) > 0:
                box = IoTComputeBox(selected_accelerator_nodes)
                neighborhood = SharedLinkCell(
                    nodes=[
                        selected_nuc_nodes,
                        selected_aot_nodes,
                        box
                    ],
                    shared_bandwidth=10000,
                    backhaul=FasterMobileConnection(self.internet)
                )
            else:
                neighborhood = SharedLinkCell(
                    nodes=[
                        selected_nuc_nodes,
                        selected_aot_nodes,
                    ],
                    shared_bandwidth=10000,
                    backhaul=FasterMobileConnection(self.internet)
                )

            neighborhoods.append(neighborhood)

        remaining_accelerators = []
        remaining_accelerators.extend(nx_nodes)
        remaining_accelerators.extend(tx2_nodes)
        remaining_accelerators.extend(nano_nodes)
        remaining_accelerators.extend(coral_nodes)

        for accelerator in remaining_accelerators:
            index = random.randint(0, len(neighborhoods) - 1)
            neighborhoods[index].nodes.append([accelerator])

            if len(nuc_nodes) > 0:
                neighborhoods[index].nodes.append([nuc_nodes[0]])
                nuc_nodes = nuc_nodes[1:]

        for nuc_node in nuc_nodes:
            index = random.randint(0, len(neighborhoods) - 1)
            neighborhoods[index].nodes.append([nuc_node])

        def get_first_non_empty_node(neighorbood):
            """
            返回 neighborhood 中第一个实际计算节点。

            存储 bucket 会登记在这个节点上；空列表和空计算盒会被跳过。

            参数:
                neighorbood: 当前 SharedLinkCell neighborhood。

            返回:
                第一个 Ether Node；找不到时返回 None。
            """
            for n in neighorbood.nodes:
                if type(n) is list and len(n) > 0:
                    if type(n) is IoTComputeBox:
                        return n.nodes[0]
                    return n[0]
            return None

        
        for neighborhood in neighborhoods:
            non_empty_node = get_first_non_empty_node(neighborhood)
            if non_empty_node is None:
                continue

            for bucket in storage.bucket_names:
                self.storage_index.mb(bucket, non_empty_node.name)

        for item in storage.data_items:
            self.storage_index.put(item)

        city = GeoCell(self.num_cells, nodes=neighborhoods, density=self.cell_density)

        return city

    def _create_aot_nodes(self, nodes: List[Node], size: int):
        """
        按固定组大小把普通边缘节点包装为 IoTComputeBox。

        参数:
            nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。
            size: 节点组或数据对象大小。 类型：int。

        返回:
            IoTComputeBox 列表。
        """
        collected = []
        aot_nodes = []
        for node in nodes:
            collected.append(node)
            if len(collected) == size:
                aot_nodes.append(IoTComputeBox(nodes=collected))
                collected = []
        if len(collected) > 0:
            aot_nodes.append(IoTComputeBox(nodes=collected))
        return aot_nodes

    def create_rockpi_aot_nodes(self):
        """
        为每个 RockPi 创建独立 IoTComputeBox。

        返回:
            RockPi IoTComputeBox 列表。
        """
        return self._create_aot_nodes(self.rockpi_nodes, 1)

    def create_rpi4_aot_nodes(self):
        """
        每两个 Raspberry Pi 4 组成一个 IoTComputeBox。

        返回:
            Raspberry Pi 4 IoTComputeBox 列表。
        """
        return self._create_aot_nodes(self.rpi4_nodes, 2)

    def create_rpi3_aot_nodes(self):
        """
        每三个 Raspberry Pi 3 组成一个 IoTComputeBox。

        返回:
            Raspberry Pi 3 IoTComputeBox 列表。
        """
        return self._create_aot_nodes(self.rpi3_nodes, 3)

    def create_cloudlet(self) -> XeonCloudlet:
        """
        创建并连接 Xeon cloudlet。

        返回:
            XeonCloudlet。
        """
        return XeonCloudlet(self.xeon_nodes, self.cloudlet_size[0], backhaul=FiberToExchange(self.internet))

    def _get_xeon_nodes(self) -> List[Node]:
        """
        返回全部 Xeon CPU 和 Xeon GPU 节点。

        返回:
            List[Node]。
        """
        xeongpus = list(filter(lambda l: 'xeongpu' in l.name, self.nodes))
        xeoncpus = list(filter(lambda l: 'xeoncpu' in l.name, self.nodes))
        xeoncpus.extend(xeongpus)
        return xeoncpus

    def _get_rpi3_nodes(self) -> List[Node]:
        """
        返回名称包含 rpi3 的节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('rpi3')

    def _get_rpi4_nodes(self) -> List[Node]:
        """
        返回名称包含 rpi4 的节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('rpi4')

    def _get_rockpi_nodes(self) -> List[Node]:
        """
        返回名称包含 rockpi 的节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('rockpi')

    def _get_nano_nodes(self) -> List[Node]:
        """
        返回名称包含 nano 的 Jetson 节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('nano')

    def _get_tx2_nodes(self) -> List[Node]:
        """
        返回名称包含 tx2 的 Jetson 节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('tx2')

    def _get_nx_nodes(self) -> List[Node]:
        """
        返回名称包含 nx 的 Jetson 节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('nx')

    def _get_nuc_nodes(self) -> List[Node]:
        """
        返回名称包含 nuc 的 Intel NUC 节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('nuc')

    def _get_coral_nodes(self) -> List[Node]:
        """
        返回名称包含 coral 的 TPU 节点。

        返回:
            List[Node]。
        """
        return self._filter_nodes('coral')

    def _filter_nodes(self, name: str) -> List[Node]:
        """
        按节点名称子串筛选场景输入节点。

        参数:
            name: 对象、节点、bucket 或配置名称。 类型：str。

        返回:
            List[Node]。
        """
        return list(filter(lambda n: name in n.name, self.nodes))
