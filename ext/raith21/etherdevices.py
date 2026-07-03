"""
文件作用：Raith21 设备到 Ether 节点的转换文件，定义 Raspberry Pi、Jetson、Xeon、Coral 等典型边缘/云节点的资源参数。
主要函数：create_rockpi、create_rpi4_node、create_coral、create_xeongpu、create_xeoncpu、create_nano、create_nx、create_node_from_device、create_aarch64_gpu、convert_to_ether_nodes、create_device_from_node、convert_to_devices。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from typing import List

from ether.blocks.nodes import create_node, counters, create_rpi3_node, create_tx2_node, create_nuc_node
from ether.core import Node

from ext.raith21.device import Device, GpuDevice
from ext.raith21.model import Location, Disk, Bins, Accelerator, Arch, Connection, CpuModel, GpuModel


def create_rockpi(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'rockpi_%d' % next(counters['rockpi'])

    return create_node(name=name,
                       cpus=6, arch='aarch64', mem='4G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'rockpi'
                       })


def create_rpi4_node(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'rpi4_%d' % next(counters['rpi4'])

    return create_node(name=name,
                       arch='arm32v7',
                       cpus=4,
                       mem='1G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'beta.kubernetes.io/arch': 'arm',
                           'locality.skippy.io/type': 'edge'
                       })


def create_coral(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'coral_%d' % next(counters['coral'])

    return create_node(name=name,
                       cpus=4, arch='aarch64', mem='1G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'coral'
                       })


def create_xeongpu(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'xeongpu_%d' % next(counters['xeongpu'])

    return create_node(name=name,
                       cpus=4, arch='x86', mem='8167784Ki',
                       labels={
                           'ether.edgerun.io/type': 'vm',
                           'ether.edgerun.io/model': 'vm',
                           'device.edgerun.io/vram': '6Gi',
                           'ether.edgerun.io/capabilities/cuda': '10',
                           'ether.edgerun.io/capabilities/gpu': 'turing',
                       })


def create_xeoncpu(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'xeoncpu_%d' % next(counters['xeoncpu'])

    return create_node(name=name,
                       cpus=4, arch='x86', mem='8167784Ki',
                       labels={
                           'ether.edgerun.io/type': 'vm',
                           'ether.edgerun.io/model': 'vm',
                       })


def create_nano(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'nano_%d' % next(counters['nano'])

    return create_node(name=name,
                       cpus=4, arch='aarch64', mem='4047252Ki',
                       labels={
                           'ether.edgerun.io/type': 'embai',
                           'ether.edgerun.io/model': 'nvidia_jetson_nano',
                           'ether.edgerun.io/capabilities/cuda': '5.3',
                           'ether.edgerun.io/capabilities/gpu': 'maxwell',
                       })


def create_nx(name=None) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：name：对象名称。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    name = name if name is not None else 'nx_%d' % next(counters['nx'])

    return create_node(name=name,
                       cpus=6, arch='aarch64', mem='8047252Ki',
                       labels={
                           'ether.edgerun.io/type': 'embai',
                           'ether.edgerun.io/model': 'nvidia_jetson_nx',
                           'ether.edgerun.io/capabilities/cuda': '7.2',
                           'ether.edgerun.io/capabilities/gpu': 'volta',
                       })


def create_node_from_device(d: Device) -> Node:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：d：单个设备对象的临时变量，用于设备到节点或节点到设备的转换。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    device = d.copy()

    def create():
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if device.arch is Arch.ARM32:
            cpu_cores = device.cores is Bins.MEDIUM or device.cores is Bins.HIGH or device.cores is Bins.VERY_HIGH
            cpu_mhz = device.cpu_mhz is Bins.HIGH or device.cpu_mhz is Bins.VERY_HIGH
            if cpu_mhz or cpu_cores:
                rpi4 = create_rpi4_node()
                device.cores = Bins.MEDIUM  
                device.ram = Bins.LOW  
                device.cpu_mhz = Bins.LOW  
                device.connection = Connection.MOBILE
                device.cpu = CpuModel.ARM
                device.network = Bins.LOW
                device.location = Location.EDGE
                return rpi4, device
            else:
                rpi3 = create_rpi3_node()
                device.cores = Bins.MEDIUM  
                device.ram = Bins.LOW  
                device.cpu_mhz = Bins.LOW  
                device.connection = Connection.MOBILE
                device.cpu = CpuModel.ARM
                device.network = Bins.LOW
                device.location = Location.EDGE
                return rpi3, device
        elif device.arch is Arch.AARCH64:
            if device.accelerator is Accelerator.GPU:
                return create_aarch64_gpu(device)
            elif device.accelerator is Accelerator.NONE:
                rockpi = create_rockpi()
                device.cores = Bins.MEDIUM  
                device.ram = Bins.LOW  
                device.cpu_mhz = Bins.MEDIUM  
                device.connection = Connection.MOBILE
                device.cpu = CpuModel.ARM
                device.network = Bins.LOW
                device.location = Location.EDGE
                device.disk = Disk.SD
                return rockpi, device
            else:
                coral = create_coral()
                device.location = Location.EDGE
                device.disk = Disk.FLASH
                device.cores = Bins.MEDIUM  
                device.ram = Bins.LOW  
                device.cpu_mhz = Bins.LOW  
                device.connection = Connection.MOBILE
                device.cpu = CpuModel.ARM
                device.network = Bins.LOW
                return coral, device
        else:
            if device.location is not Location.CLOUD:
                nuc = create_nuc_node()
                copy = Device(
                    arch=Arch.X86,
                    id=device.id,
                    cores=Bins.MEDIUM,  
                    ram=Bins.HIGH,  
                    cpu_mhz=Bins.MEDIUM,  
                    connection=Connection.MOBILE,
                    cpu=CpuModel.I7,
                    network=Bins.LOW,  
                    accelerator=Accelerator.NONE,
                    disk=Disk.NVME,
                    location=Location.EDGE
                )

                return nuc, copy
            else:
                if device.accelerator is Accelerator.GPU:
                    vm = create_xeongpu()
                    copy = GpuDevice(
                        id=device.id,
                        arch=Arch.X86,
                        accelerator=Accelerator.GPU,
                        cores=Bins.MEDIUM,  
                        location=Location.CLOUD,
                        connection=Connection.ETHERNET,
                        network=Bins.HIGH,
                        cpu_mhz=Bins.HIGH,  
                        cpu=CpuModel.XEON,
                        ram=Bins.MEDIUM,  
                        vram=Bins.MEDIUM,  
                        gpu_mhz=Bins.VERY_HIGH,  
                        gpu_model=GpuModel.TURING,
                        disk=Disk.SSD
                    )

                    vm.labels['device.edgerun.io/vram'] = '6000'
                else:
                    vm = create_xeoncpu()
                    copy = Device(
                        id=device.id,
                        arch=Arch.X86,
                        accelerator=Accelerator.NONE,
                        cores=Bins.MEDIUM,  
                        location=Location.CLOUD,
                        connection=Connection.ETHERNET,
                        network=Bins.HIGH,
                        cpu_mhz=Bins.HIGH,  
                        cpu=CpuModel.XEON,
                        ram=Bins.MEDIUM,  
                        disk=Disk.SSD
                    )
                return vm, copy

    node, device = create()

    node.labels.update(device.labels)
    if device.location is Location.CLOUD:
        node.labels['locality.skippy.io/type'] = 'cloud'
    else:
        node.labels['locality.skippy.io/type'] = 'edge'
    if device.accelerator is Accelerator.GPU:
        node.labels['capability.skippy.io/nvidia-cuda'] = '10'
        node.labels['capability.skippy.io/nvidia-gpu'] = ''
    return node


def create_aarch64_gpu(device):
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：device：单个设备对象，包含架构、资源、位置和连接方式等属性。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    adevice: GpuDevice
    adevice = device
    if device.ram is Bins.LOW or device.cpu_mhz is Bins.LOW or adevice.gpu_model is GpuModel.MAXWELL:
        node = create_nano()
        device.gpu_model = GpuModel.MAXWELL
        device.gpu_mhz = Bins.LOW  
        device.location = Location.EDGE
        device.disk = Disk.SD
        device.cores = Bins.MEDIUM  
        device.network = Bins.LOW
        device.connection = Connection.MOBILE
        device.cpu = CpuModel.ARM
        device.cpu_mhz = Bins.LOW  
        device.vram = Bins.LOW  
        device.ram = Bins.LOW  
        node.labels['device.edgerun.io/vram'] = '4000'

    elif device.gpu_model is GpuModel.PASCAL or device.cores is Bins.LOW:
        tx2_device: GpuDevice
        tx2_device = device
        node = create_tx2_node()
        tx2_device.cores = Bins.MEDIUM  
        tx2_device.ram = Bins.MEDIUM  
        tx2_device.disk = Disk.FLASH
        tx2_device.cpu_mhz = Bins.MEDIUM  
        tx2_device.connection = Connection.MOBILE
        tx2_device.cpu = CpuModel.ARM
        device.location = Location.EDGE
        tx2_device.network = Bins.LOW  
        tx2_device.vram = Bins.MEDIUM  
        tx2_device.gpu_mhz = Bins.HIGH  
        tx2_device.gpu_model = GpuModel.PASCAL
        node.labels['device.edgerun.io/vram'] = '8000'

    else:
        node = create_nx()
        device.cores = Bins.MEDIUM  
        device.ram = Bins.MEDIUM  
        device.cpu_mhz = Bins.MEDIUM  
        device.connection = Connection.MOBILE
        device.cpu = CpuModel.ARM
        device.location = Location.EDGE
        device.disk = Disk.SD
        device.network = Bins.LOW
        device.vram = Bins.MEDIUM  
        device.gpu_mhz = Bins.HIGH  
        device.gpu_model = GpuModel.TURING
        node.labels['device.edgerun.io/vram'] = '8000'

    device.vram = Bins.LOW

    return node, device


def convert_to_ether_nodes(devices: List[Device]) -> List[Node]:
    """
    函数作用：在不同对象模型之间转换数据表示。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：devices：设备对象列表，用于拓扑生成、异构度统计或节点转换。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    nodes = []
    for index, device in enumerate(devices):
        nodes.append(create_node_from_device(device))

    return nodes


def create_device_from_node(node: Node):
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：node：候选或目标节点。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    accelerator = Accelerator[node.labels['device.edgerun.io/accelerator']]
    if accelerator is Accelerator.GPU:
        return GpuDevice(
            id=node.name[:node.name.rindex('_')],
            arch=Arch[node.labels['device.edgerun.io/arch']],
            accelerator=accelerator,
            cores=Bins[node.labels['device.edgerun.io/cores']],
            location=Location[node.labels['device.edgerun.io/location']],
            connection=Connection[node.labels['device.edgerun.io/connection']],
            network=Bins[node.labels['device.edgerun.io/network']],
            cpu_mhz=Bins[node.labels['device.edgerun.io/cpu_mhz']],
            cpu=CpuModel[node.labels['device.edgerun.io/cpu']],
            ram=Bins[node.labels['device.edgerun.io/ram']],
            vram=Bins[node.labels['device.edgerun.io/vram_bin']],
            gpu_mhz=Bins[node.labels['device.edgerun.io/gpu_mhz']],
            gpu_model=GpuModel[node.labels['device.edgerun.io/gpu_model']],
            disk=Disk[node.labels['device.edgerun.io/disk']]
        )
    else:
        return Device(
            # 修正提示：这里标记了原实现中需要进一步确认的边界。
            id=node.name[:node.name.rindex('_')],
            arch=Arch[node.labels['device.edgerun.io/arch']],
            accelerator=accelerator,
            cores=Bins[node.labels['device.edgerun.io/cores']],
            location=Location[node.labels['device.edgerun.io/location']],
            connection=Connection[node.labels['device.edgerun.io/connection']],
            network=Bins[node.labels['device.edgerun.io/network']],
            cpu_mhz=Bins[node.labels['device.edgerun.io/cpu_mhz']],
            cpu=CpuModel[node.labels['device.edgerun.io/cpu']],
            ram=Bins[node.labels['device.edgerun.io/ram']],
            disk=Disk[node.labels['device.edgerun.io/disk']]
        )


def convert_to_devices(nodes: List[Node]):
    """
    函数作用：在不同对象模型之间转换数据表示。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return list(map(lambda n: create_device_from_node(n), nodes))
