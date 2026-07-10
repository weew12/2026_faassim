"""
Raith21 异构设备属性与需求模型。

本模块定义资源等级、位置、磁盘、加速器、网络连接、CPU/GPU 架构等枚举，以及用于描述目标设备分布的 Requirements 数据类。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict

"""
Bins:    |    LOW     |    MEDIUM    |     HIGH     | VERY_HIGH

Cores:   | 1-2        |   4 - 8      |  16 - 32     | > 32
RAM:     | 1-2        |   4 - 8      |  16 - 32     | > 32
CpuMhz:  | <= 1.5     |   1.6 - 2.2  |     < 3.5    | > 3.5
GpuMHz:  | <= 1000    |   <= 1200    |  <= 1500     | > 1700
VRAM:    | <= 2       |   4 - 8      |   < 32       | > 32    
Network: | <= 150Mbps | <= 500 Mbps  | <=1 Gbit     | >= 10 Gbit 
"""


class Bins(Enum):
    """
    离散资源能力等级：LOW、MEDIUM、HIGH、VERY_HIGH。
    """
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4


class Location(Enum):
    """
    设备部署位置：CLOUD、EDGE、MEC、MOBILE。
    """
    CLOUD = 1
    EDGE = 2
    MEC = 3
    MOBILE = 4


class Disk(Enum):
    """
    存储介质类型：HDD、SSD、NVME、FLASH、SD。
    """
    HDD = 1
    SSD = 2
    NVME = 3
    FLASH = 4
    SD = 5


class Accelerator(Enum):
    """
    加速器类型：NONE、GPU、TPU。
    """
    NONE = 1
    GPU = 2
    TPU = 3


class Connection(Enum):
    """
    网络接入方式：MOBILE、WIFI、ETHERNET。
    """
    MOBILE = 1
    WIFI = 2
    ETHERNET = 3


class Arch(Enum):
    """
    CPU 指令集架构：ARM32、X86、AARCH64。
    """
    ARM32 = 1
    X86 = 2
    AARCH64 = 3


class GpuModel(Enum):
    """
    GPU 微架构类别：TURING、PASCAL、MAXWELL、VOLTA。
    """
    TURING = 1
    PASCAL = 2
    MAXWELL = 3
    VOLTA = 4


class CpuModel(Enum):
    """
    CPU 类型：I7、XEON、ARM。
    """
    I7 = 1
    XEON = 2
    ARM = 3


@dataclass
class Requirements:
    """
    目标设备属性概率向量。

    每个字段把枚举取值映射到概率，用于生成设备并计算实际集群与目标分布之间的异构度。

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
    arch: Dict[Arch, float]
    accelerator: Dict[Accelerator, float]
    cores: Dict[Bins, float]
    disk: Dict[Disk, float]
    location: Dict[Location, float]
    connection: Dict[Connection, float]
    network: Dict[Bins, float]
    cpu_mhz: Dict[Bins, float]
    cpu: Dict[CpuModel, float]
    ram: Dict[Bins, float]
    gpu_vram: Dict[Bins, float]
    gpu_mhz: Dict[Bins, float]
    gpu_model: Dict[GpuModel, float]

    def __str__(self):
        """
        把 Requirements 各属性概率格式化为便于检查的多段文本。

        返回:
            计算、查询或构造得到的结果。
        """
        def join(d: Dict) -> str:
            """
            把单个属性概率字典格式化为多行文本。

            参数:
                d: 待转换的 Device 或属性字典。 类型：Dict。

            返回:
                str。
            """
            return "\n".join(['%s:: %s' % (key, value) for (key, value) in d.items()])

        text = "---------------------------"
        for name, c in self.characteristics:
            text += f'\n--------{name}---------\n'
            text += join(c)
            text += '\n'
        return text

    def __map(self, d: Dict[Enum, float]) -> Dict[str, float]:
        """
        把枚举键转换为枚举名称字符串。

        参数:
            d: 待转换的 Device 或属性字典。 类型：Dict[Enum, float]。

        返回:
            Dict[str, float]。
        """
        data = {}
        for k, v in d.items():
            data[f'{str(k.name)}'] = v
        return data

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """
        把 Requirements 转换为以 device.edgerun.io 标签为键的普通字典。

        返回:
            Dict[str, Dict[str, float]]。
        """
        return {
            'device.edgerun.io/arch': self.__map(self.arch),
            'device.edgerun.io/accelerator': self.__map(self.accelerator),
            'device.edgerun.io/cores': self.__map(self.cores),
            'device.edgerun.io/disk': self.__map(self.disk),
            'device.edgerun.io/location': self.__map(self.location),
            'device.edgerun.io/connection': self.__map(self.connection),
            'device.edgerun.io/network': self.__map(self.network),
            'device.edgerun.io/cpu_mhz': self.__map(self.cpu_mhz),
            'device.edgerun.io/cpu': self.__map(self.cpu),
            'device.edgerun.io/ram': self.__map(self.ram),
            'device.edgerun.io/vram_bin': self.__map(self.gpu_vram),
            'device.edgerun.io/gpu_mhz': self.__map(self.gpu_mhz),
            'device.edgerun.io/gpu_model': self.__map(self.gpu_model),
        }

    @property
    def characteristics(self):
        """
        返回异构度计算使用的枚举类型与概率字典列表。

        返回:
            计算、查询或构造得到的结果。
        """
        return [
            (Arch, self.arch),
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

    @staticmethod
    def fields():
        """
        返回 Requirements 字段名及对应枚举类型。

        返回:
            计算、查询或构造得到的结果。
        """
        return [
            ('arch', Arch),
            ('accelerator', Accelerator),
            ('cores', Bins),
            ('disk', Disk),
            ('location', Location),
            ('connection', Connection),
            ('network', Bins),
            ('cpu_mhz', Bins),
            ('cpu', CpuModel),
            ('ram', Bins),
            ('gpu_vram', Bins),
            ('gpu_mhz', Bins),
            ('gpu_model', GpuModel)
        ]
