"""
文件作用：Raith21 扩展实验的设备属性与需求模型，定义架构、位置、磁盘、加速器、连接方式、GPU/CPU 型号和资源需求枚举。
主要类：Bins、Location、Disk、Accelerator、Connection、Arch、GpuModel、CpuModel、Requirements。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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
    类作用：Bins 枚举类，定义 bins 相关的可选取值。
    继承关系：Enum。
    核心字段：LOW：低资源或低能力等级。；MEDIUM：中等资源或能力等级。；HIGH：高资源或能力等级。；VERY_HIGH：很高资源或能力等级。。
    """
    # 字段说明：LOW：低资源或低能力等级。
    LOW = 1
    # 字段说明：MEDIUM：中等资源或能力等级。
    MEDIUM = 2
    # 字段说明：HIGH：高资源或能力等级。
    HIGH = 3
    # 字段说明：VERY_HIGH：很高资源或能力等级。
    VERY_HIGH = 4


class Location(Enum):
    """
    类作用：Location 枚举类，定义 location 相关的可选取值。
    继承关系：Enum。
    核心字段：CLOUD：云端或中心数据中心位置。；EDGE：边缘侧位置。；MEC：多接入边缘计算位置。；MOBILE：移动网络连接。。
    """
    # 字段说明：CLOUD：云端或中心数据中心位置。
    CLOUD = 1
    # 字段说明：EDGE：边缘侧位置。
    EDGE = 2
    # 字段说明：MEC：多接入边缘计算位置。
    MEC = 3
    # 字段说明：MOBILE：移动网络连接。
    MOBILE = 4


class Disk(Enum):
    """
    类作用：Disk 枚举类，定义 disk 相关的可选取值。
    继承关系：Enum。
    核心字段：HDD：机械硬盘。；SSD：固态硬盘。；NVME：NVMe 高速固态盘。；FLASH：闪存存储。；SD：SD 卡存储。。
    """
    # 字段说明：HDD：机械硬盘。
    HDD = 1
    # 字段说明：SSD：固态硬盘。
    SSD = 2
    # 字段说明：NVME：NVMe 高速固态盘。
    NVME = 3
    # 字段说明：FLASH：闪存存储。
    FLASH = 4
    # 字段说明：SD：SD 卡存储。
    SD = 5


class Accelerator(Enum):
    """
    类作用：Accelerator 枚举类，定义 accelerator 相关的可选取值。
    继承关系：Enum。
    核心字段：NONE：无专用加速器。；GPU：GPU 加速器。；TPU：TPU 加速器。。
    """
    # 字段说明：NONE：无专用加速器。
    NONE = 1
    # 字段说明：GPU：GPU 加速器。
    GPU = 2
    # 字段说明：TPU：TPU 加速器。
    TPU = 3


class Connection(Enum):
    """
    类作用：Connection 枚举类，定义 connection 相关的可选取值。
    继承关系：Enum。
    核心字段：MOBILE：移动网络连接。；WIFI：WiFi 无线连接。；ETHERNET：有线以太网连接。。
    """
    # 字段说明：MOBILE：移动网络连接。
    MOBILE = 1
    # 字段说明：WIFI：WiFi 无线连接。
    WIFI = 2
    # 字段说明：ETHERNET：有线以太网连接。
    ETHERNET = 3


class Arch(Enum):
    """
    类作用：Arch 枚举类，定义 arch 相关的可选取值。
    继承关系：Enum。
    核心字段：ARM32：32 位 ARM 架构。；X86：x86 架构。；AARCH64：64 位 ARM 架构。。
    """
    # 字段说明：ARM32：32 位 ARM 架构。
    ARM32 = 1
    # 字段说明：X86：x86 架构。
    X86 = 2
    # 字段说明：AARCH64：64 位 ARM 架构。
    AARCH64 = 3


class GpuModel(Enum):
    """
    类作用：GpuModel 枚举类，定义 gpu、model 相关的可选取值。
    继承关系：Enum。
    核心字段：TURING：NVIDIA Turing GPU。；PASCAL：NVIDIA Pascal GPU。；MAXWELL：NVIDIA Maxwell GPU。；VOLTA：NVIDIA Volta GPU。。
    """
    # 字段说明：TURING：NVIDIA Turing GPU。
    TURING = 1
    # 字段说明：PASCAL：NVIDIA Pascal GPU。
    PASCAL = 2
    # 字段说明：MAXWELL：NVIDIA Maxwell GPU。
    MAXWELL = 3
    # 字段说明：VOLTA：NVIDIA Volta GPU。
    VOLTA = 4


class CpuModel(Enum):
    """
    类作用：CpuModel 枚举类，定义 cpu、model 相关的可选取值。
    继承关系：Enum。
    核心字段：I7：Intel i7 CPU。；XEON：Intel Xeon CPU。；ARM：ARM CPU。。
    """
    # 字段说明：I7：Intel i7 CPU。
    I7 = 1
    # 字段说明：XEON：Intel Xeon CPU。
    XEON = 2
    # 字段说明：ARM：ARM CPU。
    ARM = 3


@dataclass
class Requirements:
    """
    类作用：函数或设备需求向量，按架构、加速器、资源、位置和连接方式组织调度匹配字段。
    核心字段：arch：CPU 架构属性，例如 x86、arm32、aarch64。；accelerator：加速器能力，例如 GPU、TPU 或无。；cores：CPU 核心数量等级或数值。；disk：存储介质类型。；location：设备所处层级，例如云、边缘、MEC 或移动端。；connection：网络接入方式，例如以太网、WiFi 或移动网络。；network：网络吞吐能力等级或数值。；cpu_mhz：CPU 主频等级或数值。 等。
    核心方法：__str__、__map、to_dict、characteristics、fields。
    """
    # 字段说明：arch：CPU 架构属性，例如 x86、arm32、aarch64。
    arch: Dict[Arch, float]
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
    gpu_vram: Dict[Bins, float]
    # 字段说明：gpu_mhz：GPU 主频。
    gpu_mhz: Dict[Bins, float]
    # 字段说明：gpu_model：GPU 型号。
    gpu_model: Dict[GpuModel, float]

    def __str__(self):
        """
        函数作用：将对象转换为便于日志和调试阅读的字符串。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        def join(d: Dict) -> str:
            """
            函数作用：处理 join 相关业务逻辑。
            关键流程：
            - 返回计算结果或被创建的业务对象，供上层流程继续使用。
            参数：d：单个设备对象的临时变量，用于设备到节点或节点到设备的转换。。
            返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：处理 map 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：d：单个设备对象的临时变量，用于设备到节点或节点到设备的转换。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        data = {}
        for k, v in d.items():
            data[f'{str(k.name)}'] = v
        return data

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """
        函数作用：把需求向量转换为普通字典，便于序列化或统计。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：返回参与异构度计算的需求属性集合。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：返回需求对象包含的字段名集合。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
