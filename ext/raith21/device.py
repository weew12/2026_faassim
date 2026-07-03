"""
文件作用：Raith21 设备抽象文件，将随机生成或真实设备参数封装为 Device/GpuDevice，并转换为调度标签。
主要类：ArchProperties、Device、GpuDevice。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from dataclasses import dataclass, field
from typing import Dict

from ext.raith21.model import Location, Disk, Bins, Accelerator, Arch, Connection, CpuModel, GpuModel


@dataclass
class ArchProperties:
    """
    类作用：设备属性概率集合，描述某种 CPU 架构下各类资源属性出现的概率。
    核心字段：arch：CPU 架构属性，例如 x86、arm32、aarch64。；accelerator：加速器能力，例如 GPU、TPU 或无。；cores：CPU 核心数量等级或数值。；disk：存储介质类型。；location：设备所处层级，例如云、边缘、MEC 或移动端。；connection：网络接入方式，例如以太网、WiFi 或移动网络。；network：网络吞吐能力等级或数值。；cpu_mhz：CPU 主频等级或数值。 等。
    核心方法：values。
    """
    # 字段说明：arch：CPU 架构属性，例如 x86、arm32、aarch64。
    arch: Arch
    # 字段说明：accelerator：加速器能力，例如 GPU、TPU 或无。
    accelerator: Dict[Accelerator, float]
    # 字段说明：cores：CPU 核心数量等级或数值。
    cores: Dict[Bins, float]
    # 字段说明：disk：存储介质类型。
    disk: Dict[Disk, float]
    # 字段说明：location：设备所处层级，例如云、边缘、MEC 或移动端。
    location: Dict[Location, float]
    # 字段说明：connection：网络接入方式，例如以太网、WiFi 或移动网络。
    connection: Dict[Connection, float]
    # 字段说明：network：网络吞吐能力等级或数值。
    network: Dict[Bins, float]
    # 字段说明：cpu_mhz：CPU 主频等级或数值。
    cpu_mhz: Dict[Bins, float]
    # 字段说明：cpu：CPU 使用量或 CPU 资源请求。
    cpu: Dict[CpuModel, float]
    # 字段说明：ram：内存使用量。
    ram: Dict[Bins, float]
    # 字段说明：gpu_vram：GPU 显存大小。
    gpu_vram: Dict[Bins, float] = field(default_factory=dict)
    # 字段说明：gpu_mhz：GPU 主频。
    gpu_mhz: Dict[Bins, float] = field(default_factory=dict)
    # 字段说明：gpu_model：GPU 型号。
    gpu_model: Dict[GpuModel, float] = field(default_factory=dict)

    @property
    def values(self):
        """
        函数作用：返回属性对象内部的枚举概率映射。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return [
            (Accelerator, self.accelerator),
            (Bins, self.cores),
            (Disk, self.disk),
            (Location, self.location),
            (Connection, self.connection),
            (Bins, self.network),
            (Bins, self.cpu_mhz),
            (Bins, self.cpu),
            (Bins, self.ram),
            (Bins, self.gpu_vram),
            (Bins, self.gpu_mhz),
            (GpuModel, self.gpu_model)
        ]


@dataclass
class Device:
    """
    类作用：异构设备描述对象，保存架构、核心数、位置、网络、CPU、内存等基础属性。
    核心字段：id：设备或请求的唯一标识。；arch：CPU 架构属性，例如 x86、arm32、aarch64。；accelerator：加速器能力，例如 GPU、TPU 或无。；cores：CPU 核心数量等级或数值。；disk：存储介质类型。；location：设备所处层级，例如云、边缘、MEC 或移动端。；connection：网络接入方式，例如以太网、WiFi 或移动网络。；network：网络吞吐能力等级或数值。 等。
    核心方法：labels、copy。
    """
    # 字段说明：id：设备或请求的唯一标识。
    id: str
    # 字段说明：arch：CPU 架构属性，例如 x86、arm32、aarch64。
    arch: Arch
    # 字段说明：accelerator：加速器能力，例如 GPU、TPU 或无。
    accelerator: Accelerator
    # 字段说明：cores：CPU 核心数量等级或数值。
    cores: Bins
    # 字段说明：disk：存储介质类型。
    disk: Disk
    # 字段说明：location：设备所处层级，例如云、边缘、MEC 或移动端。
    location: Location
    # 字段说明：connection：网络接入方式，例如以太网、WiFi 或移动网络。
    connection: Connection
    # 字段说明：network：网络吞吐能力等级或数值。
    network: Bins
    # 字段说明：cpu_mhz：CPU 主频等级或数值。
    cpu_mhz: Bins
    # 字段说明：cpu：CPU 使用量或 CPU 资源请求。
    cpu: CpuModel
    # 字段说明：ram：内存使用量。
    ram: Bins

    @property
    def labels(self) -> Dict[str, str]:
        """
        函数作用：把设备属性转换为调度器可识别的标签集合。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return {
            'device.edgerun.io/arch': str(self.arch.name),
            'device.edgerun.io/accelerator': str(self.accelerator.name),
            'device.edgerun.io/cores': str(self.cores.name),
            'device.edgerun.io/location': str(self.location.name),
            'device.edgerun.io/connection': str(self.connection.name),
            'device.edgerun.io/network': str(self.network.name),
            'device.edgerun.io/cpu_mhz': str(self.cpu_mhz.name),
            'device.edgerun.io/cpu': str(self.cpu.name),
            'device.edgerun.io/ram': str(self.ram.name),
            'device.edgerun.io/disk': str(self.disk.name)
        }

    def copy(self):
        """
        函数作用：复制当前对象，避免外部修改影响原状态。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return Device(
            id=self.id,
            arch=self.arch,
            accelerator=self.accelerator,
            cores=self.cores,
            disk=self.disk,
            location=self.location,
            connection=self.connection,
            network=self.network,
            cpu_mhz=self.cpu_mhz,
            cpu=self.cpu,
            ram=self.ram
        )


@dataclass
class GpuDevice(Device):
    """
    类作用：带 GPU 的设备描述对象，在 Device 基础上增加显存、GPU 频率和 GPU 型号。
    继承关系：Device。
    核心字段：vram：GPU 显存容量。；gpu_mhz：GPU 主频。；gpu_model：GPU 型号。。
    核心方法：labels、copy。
    """
    # 字段说明：vram：GPU 显存容量。
    vram: Bins
    # 字段说明：gpu_mhz：GPU 主频。
    gpu_mhz: Bins
    # 字段说明：gpu_model：GPU 型号。
    gpu_model: GpuModel

    @property
    def labels(self) -> Dict[str, str]:
        """
        函数作用：把设备属性转换为调度器可识别的标签集合。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        super_labels = super().labels
        super_labels['device.edgerun.io/vram_bin'] = str(self.vram.name)
        super_labels['device.edgerun.io/gpu_mhz'] = str(self.gpu_mhz.name)
        super_labels['device.edgerun.io/gpu_model'] = str(self.gpu_model.name)
        return super_labels

    def copy(self):
        """
        函数作用：复制当前对象，避免外部修改影响原状态。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return GpuDevice(
            id=self.id,
            arch=self.arch,
            accelerator=self.accelerator,
            cores=self.cores,
            disk=self.disk,
            location=self.location,
            connection=self.connection,
            network=self.network,
            cpu_mhz=self.cpu_mhz,
            cpu=self.cpu,
            ram=self.ram,
            vram=self.vram,
            gpu_mhz=self.gpu_mhz,
            gpu_model=self.gpu_model
        )
