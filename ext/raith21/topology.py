"""
文件作用：Raith21 拓扑构造文件，生成云、城市感知、异构边缘集群等实验拓扑，并组合 Ether 节点、链路和网络单元。
主要类：XeonCloudlet、FasterMobileConnection、HeterogeneousUrbanSensingScenario。
主要函数：all_internet_topology、urban_sensing_topology、parts。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


def all_internet_topology(nodes: List[Node]) -> Topology:
    """
    函数作用：处理 all、internet、topology 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    t = Topology()
    for node in nodes:
        cell = LANCell(nodes=[node], backhaul='internet')
        t.add(cell)
    t.init_docker_registry()

    return t


def urban_sensing_topology(nodes: List[Node], storage_index: StorageIndex) -> Topology:
    """
    函数作用：处理 urban、sensing、topology 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；storage_index：存储节点索引，用于模拟函数输入/输出数据传输。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    t = Topology()
    HeterogeneousUrbanSensingScenario(nodes, storage_index).materialize(t)
    t.init_docker_registry()

    return t


class XeonCloudlet(LANCell):

    """
    类作用：XeonCloudlet 类，封装 xeon、cloudlet 相关状态和业务操作。
    继承关系：LANCell。
    核心方法：__init__、create_nodes、_create_identity。
    """
    def __init__(self, xeons: List[Node], xeon_vms_per_rack=5, backhaul=None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：name、racks、xeon_vms_per_rack、xeons。
        参数：xeons：Xeon 服务器数量或节点集合。；xeon_vms_per_rack：每个机架上生成的 Xeon 虚拟机数量。；backhaul：表示 backhaul，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.name：业务对象名称，通常用于函数、节点、镜像或实验标识。
        self.name = None
        self._create_identity()
        # 字段说明：self.xeons：Xeon 服务器数量或节点集合。
        self.xeons = xeons
        # 字段说明：self.xeon_vms_per_rack：每个机架上生成的 Xeon 虚拟机数量。
        self.xeon_vms_per_rack = xeon_vms_per_rack
        # 字段说明：self.racks：机架集合，用于云/边缘集群拓扑生成。
        self.racks = int(len(self.xeons) / self.xeon_vms_per_rack)
        nodes = self.create_nodes()

        super().__init__(nodes, backhaul=backhaul)

    def create_nodes(self) -> List[LANCell]:
        """
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：处理 create、identity 相关业务逻辑。
        关键流程：
        - 写入对象字段：name、nr、switch。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if self.name is None:
            # 字段说明：self.nr：编号或数量参数，常用于生成节点身份。
            self.nr = next(counters['cloudlet'])
            # 字段说明：self.name：业务对象名称，通常用于函数、节点、镜像或实验标识。
            self.name = 'cloudlet_%d' % self.nr
            # 字段说明：self.switch：交换机节点，用于连接同一子网或机架内设备。
            self.switch = 'switch_%s' % self.name


def parts(a, b):
    """
    函数作用：处理 parts 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：a：表示 a，在当前业务流程中作为输入参数、状态字段或计算结果使用。；b：表示 b，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    q, r = divmod(a, b)
    return [q + 1] * r + [q] * (b - r)


class FasterMobileConnection(UpDownLink):

    """
    类作用：FasterMobileConnection 类，封装 faster、mobile、connection 相关状态和业务操作。
    继承关系：UpDownLink。
    核心方法：__init__。
    """
    def __init__(self, backhaul='internet') -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        参数：backhaul：表示 backhaul，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__(250, 250, backhaul)


class HeterogeneousUrbanSensingScenario(UrbanSensingScenario):

    """
    类作用：HeterogeneousUrbanSensingScenario 类，封装 heterogeneous、urban、sensing、scenario 相关状态和业务操作。
    继承关系：UrbanSensingScenario。
    核心方法：__init__、create_city、_create_aot_nodes、create_rockpi_aot_nodes、create_rpi4_aot_nodes、create_rpi3_aot_nodes、create_cloudlet、_get_xeon_nodes、_get_rpi3_nodes、_get_rpi4_nodes、_get_rockpi_nodes、_get_nano_nodes 等。
    """
    def __init__(self, nodes: List[Node], storage_index: StorageIndex, num_cells=default_num_cells,
                 cell_density=default_cell_density,
                 cloudlet_size=default_cloudlet_size, internet='internet') -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：coral_nodes、nano_nodes、nodes、nuc_nodes、nx_nodes、rockpi_nodes、rpi3_nodes、rpi4_nodes、storage_index、tx2_nodes、xeon_nodes。
        参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；storage_index：存储节点索引，用于模拟函数输入/输出数据传输。；num_cells：表示 num、cells，在当前业务流程中作为输入参数、状态字段或计算结果使用。；cell_density：表示 cell、density，在当前业务流程中作为输入参数、状态字段或计算结果使用。；cloudlet_size：表示 cloudlet、size，在当前业务流程中作为输入参数、状态字段或计算结果使用。；internet：表示 internet，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。
        self.nodes = nodes
        # 字段说明：self.storage_index：存储节点索引，用于模拟函数输入/输出数据传输。
        self.storage_index = storage_index
        # 字段说明：self.xeon_nodes：Xeon 节点集合。
        self.xeon_nodes = self._get_xeon_nodes()
        # 字段说明：self.rpi3_nodes：Raspberry Pi 3 节点集合。
        self.rpi3_nodes = self._get_rpi3_nodes()
        # 字段说明：self.rpi4_nodes：Raspberry Pi 4 节点集合。
        self.rpi4_nodes = self._get_rpi4_nodes()
        # 字段说明：self.rockpi_nodes：RockPi 节点集合。
        self.rockpi_nodes = self._get_rockpi_nodes()
        # 字段说明：self.tx2_nodes：Jetson TX2 节点集合。
        self.tx2_nodes = self._get_tx2_nodes()
        # 字段说明：self.nx_nodes：Jetson NX 节点集合。
        self.nx_nodes = self._get_nx_nodes()
        # 字段说明：self.nano_nodes：Jetson Nano 节点集合。
        self.nano_nodes = self._get_nano_nodes()
        # 字段说明：self.coral_nodes：Coral DevBoard 节点集合。
        self.coral_nodes = self._get_coral_nodes()
        # 字段说明：self.nuc_nodes：Intel NUC 节点集合。
        self.nuc_nodes = self._get_nuc_nodes()

        super().__init__(num_cells, cell_density, cloudlet_size, internet)

    def create_city(self) -> GeoCell:
        """
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 使用随机采样生成设备属性、请求间隔或性能取值。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
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
                """
                函数作用：处理 select、nodes 相关业务逻辑。
                关键流程：
                - 返回计算结果或被创建的业务对象，供上层流程继续使用。
                参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；n：数量参数。。
                返回：与该业务步骤对应的对象、指标或计算结果。
                """
                if n > len(nodes):
                    diff = n - len(nodes)
                    n -= diff
                return nodes[selected_size:], nodes[:selected_size]

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
            函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
            关键流程：
            - 返回计算结果或被创建的业务对象，供上层流程继续使用。
            参数：neighorbood：表示 neighorbood，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
            返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：处理 create、aot、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。；size：请求数据大小，影响网络传输耗时。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._create_aot_nodes(self.rockpi_nodes, 1)

    def create_rpi4_aot_nodes(self):
        """
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._create_aot_nodes(self.rpi4_nodes, 2)

    def create_rpi3_aot_nodes(self):
        """
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._create_aot_nodes(self.rpi3_nodes, 3)

    def create_cloudlet(self) -> XeonCloudlet:
        """
        函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return XeonCloudlet(self.xeon_nodes, self.cloudlet_size[0], backhaul=FiberToExchange(self.internet))

    def _get_xeon_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、xeon、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        xeongpus = list(filter(lambda l: 'xeongpu' in l.name, self.nodes))
        xeoncpus = list(filter(lambda l: 'xeoncpu' in l.name, self.nodes))
        xeoncpus.extend(xeongpus)
        return xeoncpus

    def _get_rpi3_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、rpi3、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('rpi3')

    def _get_rpi4_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、rpi4、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('rpi4')

    def _get_rockpi_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、rockpi、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('rockpi')

    def _get_nano_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、nano、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('nano')

    def _get_tx2_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、tx2、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('tx2')

    def _get_nx_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、nx、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('nx')

    def _get_nuc_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、nuc、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('nuc')

    def _get_coral_nodes(self) -> List[Node]:
        """
        函数作用：处理 get、coral、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self._filter_nodes('coral')

    def _filter_nodes(self, name: str) -> List[Node]:
        """
        函数作用：处理 filter、nodes 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：name：对象名称。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return list(filter(lambda n: name in n.name, self.nodes))
