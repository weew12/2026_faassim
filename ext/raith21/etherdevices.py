"""
Raith21 设备与 Ether 节点之间的转换。

本模块既提供论文中典型硬件节点的固定配置，也能把随机生成的 Device 转换为 Ether Node，并支持从节点反向恢复设备属性。
"""

from typing import List

from ether.blocks.nodes import create_node, counters, create_rpi3_node, create_tx2_node, create_nuc_node
from ether.core import Node

from ext.raith21.device import Device, GpuDevice
from ext.raith21.model import Location, Disk, Bins, Accelerator, Arch, Connection, CpuModel, GpuModel


def create_rockpi(name=None) -> Node:
    """
    创建论文设定的 RockPi Ether 节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建 Raspberry Pi 4 Ether 节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建带 Edge TPU 能力的 Coral Ether 节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建带 NVIDIA GPU 的 Xeon 云节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建仅使用 CPU 的 Xeon 云节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建 Jetson Nano 边缘 GPU 节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    创建 Jetson Xavier NX 边缘 GPU 节点。

    参数:
        name: 对象、节点、bucket 或配置名称。

    返回:
        Node。
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
    把随机 Device 的容量和属性转换为 Ether Node。

    参数:
        d: 待转换的 Device 或属性字典。 类型：Device。

    返回:
        Node。
    """
    device = d.copy()

    def create():
        """
        根据函数容器创建对应 FunctionSimulator。

        返回:
            计算、查询或构造得到的结果。
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
    根据 GPU 设备能力创建 AArch64 Ether 节点。

    参数:
        device: 异构设备对象。

    返回:
        计算、查询或构造得到的结果。
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
    批量把 Device 列表转换为 Ether Node 列表。

    参数:
        devices: 异构设备集合。 类型：List[Device]。

    返回:
        List[Node]。
    """
    nodes = []
    for index, device in enumerate(devices):
        nodes.append(create_node_from_device(device))

    return nodes


def create_device_from_node(node: Node):
    """
    根据 Ether Node 的名称、标签和容量恢复 Device/GpuDevice。

    参数:
        node: 候选 Skippy 节点。 类型：Node。

    返回:
        计算、查询或构造得到的结果。
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
    批量把 Ether Node 列表转换为 Device 列表。

    参数:
        nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。

    返回:
        计算、查询或构造得到的结果。
    """
    return list(map(lambda n: create_device_from_node(n), nodes))
