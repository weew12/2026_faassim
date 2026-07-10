"""
异构设备领域模型。

本模块用 ArchProperties、Device 和 GpuDevice 表示架构、计算能力、存储、位置、网络和 GPU 属性，并提供转换为 Skippy 节点标签的入口。
"""

from dataclasses import dataclass, field
from typing import Dict

from ext.raith21.model import Location, Disk, Bins, Accelerator, Arch, Connection, CpuModel, GpuModel


@dataclass
class ArchProperties:
    """
    设备属性概率配置。

    每个字段保存某类设备属性的候选值及其概率，用于 GeneratorSettings 随机生成异构设备。

    关键字段:
        arch: CPU 架构及其概率分布。
        accelerator: 加速器类型及其概率分布。
        cores: CPU 核心数等级及其概率分布。
        disk: 磁盘类型及其概率分布。
        location: 设备位置类型及其概率分布。
        connection: 网络接入方式及其概率分布。
        network: 网络能力等级及其概率分布。
        cpu_mhz: CPU 主频等级及其概率分布。
        cpu: CPU 型号或 CPU 占用画像。
        ram: 内存等级或内存占用画像。
        gpu_vram: GPU 显存等级及其概率分布。
        gpu_mhz: GPU 主频等级及其概率分布。
        gpu_model: GPU 型号及其概率分布。
    """
    arch: Arch
    accelerator: Dict[Accelerator, float]
    cores: Dict[Bins, float]
    disk: Dict[Disk, float]
    location: Dict[Location, float]
    connection: Dict[Connection, float]
    network: Dict[Bins, float]
    cpu_mhz: Dict[Bins, float]
    cpu: Dict[CpuModel, float]
    ram: Dict[Bins, float]
    gpu_vram: Dict[Bins, float] = field(default_factory=dict)
    gpu_mhz: Dict[Bins, float] = field(default_factory=dict)
    gpu_model: Dict[GpuModel, float] = field(default_factory=dict)

    @property
    def values(self):
        """
        返回各设备属性的候选值到概率映射。

        返回:
            计算、查询或构造得到的结果。
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
    通用计算设备。

    保存设备的架构、CPU、内存、磁盘、位置、网络和加速器属性，并可转换为 Skippy 使用的 device.edgerun.io 标签。

    关键字段:
        id: 设备唯一编号。
        arch: CPU 架构及其概率分布。
        accelerator: 加速器类型及其概率分布。
        cores: CPU 核心数等级及其概率分布。
        disk: 磁盘类型及其概率分布。
        location: 设备位置类型及其概率分布。
        connection: 网络接入方式及其概率分布。
        network: 网络能力等级及其概率分布。
        cpu_mhz: CPU 主频等级及其概率分布。
        cpu: CPU 型号或 CPU 占用画像。
        ram: 内存等级或内存占用画像。
    """
    id: str
    arch: Arch
    accelerator: Accelerator
    cores: Bins
    disk: Disk
    location: Location
    connection: Connection
    network: Bins
    cpu_mhz: Bins
    cpu: CpuModel
    ram: Bins

    @property
    def labels(self) -> Dict[str, str]:
        """
        把设备属性编码为 Skippy 节点标签。

        返回:
            Dict[str, str]。
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
        返回当前设备对象的独立副本。

        返回:
            计算、查询或构造得到的结果。
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
    带 GPU 细节的设备。

    在 Device 基础上增加显存、GPU 主频和 GPU 型号，并把这些能力编码到节点标签中。

    关键字段:
        vram: GPU 显存容量。
        gpu_mhz: GPU 主频等级及其概率分布。
        gpu_model: GPU 型号及其概率分布。
    """
    vram: Bins
    gpu_mhz: Bins
    gpu_model: GpuModel

    @property
    def labels(self) -> Dict[str, str]:
        """
        把设备属性编码为 Skippy 节点标签。

        返回:
            Dict[str, str]。
        """
        super_labels = super().labels
        super_labels['device.edgerun.io/vram_bin'] = str(self.vram.name)
        super_labels['device.edgerun.io/gpu_mhz'] = str(self.gpu_mhz.name)
        super_labels['device.edgerun.io/gpu_model'] = str(self.gpu_model.name)
        return super_labels

    def copy(self):
        """
        返回当前设备对象的独立副本。

        返回:
            计算、查询或构造得到的结果。
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
