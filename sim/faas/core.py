"""
文件作用：FaaS 领域模型核心文件，定义函数、镜像、容器、副本、部署、请求/响应、资源配置、生命周期状态以及 FaaS 系统抽象接口。
主要类：FunctionState、Resources、FunctionResourceCharacterization、FunctionCharacterization、FunctionImage、DeploymentRanking、ResourceConfiguration、KubernetesResourceConfiguration、Function、FunctionContainer、ScalingConfiguration、FunctionDeployment 等。
主要函数：counter。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import abc
import enum
import logging
from collections import defaultdict
from typing import List, Dict, NamedTuple, Optional

from ether.core import Node as EtherNode
from ether.util import parse_size_string
from skippy.core.model import Pod

from sim.core import Environment, NodeState
from sim.oracle.oracle import FetOracle, ResourceOracle

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)

# 字段说明：Node：表示 node，在当前业务流程中作为输入参数、状态字段或计算结果使用。
Node = EtherNode


def counter(start: int = 1):
    """
    函数作用：处理 counter 相关业务逻辑。
    关键流程：
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：start：函数调用或生命周期阶段开始时间。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    n = start
    while True:
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield n
        n += 1


class FunctionState(enum.Enum):
    """
    类作用：函数副本生命周期枚举，用于标记副本从构造、启动、运行到挂起的状态。
    继承关系：enum.Enum。
    核心字段：CONCEIVED：副本刚被创建，尚未完成调度和启动。；STARTING：副本正在执行镜像拉取、容器启动或 setup。；RUNNING：副本已经可接收函数请求。；SUSPENDED：副本被挂起或下线，不再参与调用。。
    """
    # 字段说明：CONCEIVED：副本刚被创建，尚未完成调度和启动。
    CONCEIVED = 1
    # 字段说明：STARTING：副本正在执行镜像拉取、容器启动或 setup。
    STARTING = 2
    # 字段说明：RUNNING：副本已经可接收函数请求。
    RUNNING = 3
    # 字段说明：SUSPENDED：副本被挂起或下线，不再参与调用。
    SUSPENDED = 4


class Resources:
    """
    类作用：Kubernetes 风格资源请求对象，保存 CPU 毫核和内存字节数，用于调度容量判断。
    核心字段：memory：内存大小或内存资源请求。；cpu：CPU 使用量或 CPU 资源请求。。
    核心方法：__init__、__str__、from_str。
    """
    # 字段说明：memory：内存大小或内存资源请求。
    memory: int
    # 字段说明：cpu：CPU 使用量或 CPU 资源请求。
    cpu: int

    def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1 * 1024 * 1024):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：cpu、memory。
        参数：cpu_millis：表示 cpu、millis，在当前业务流程中作为输入参数、状态字段或计算结果使用。；memory：内存请求或使用量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.memory：内存大小或内存资源请求。
        self.memory = memory
        # 字段说明：self.cpu：CPU 使用量或 CPU 资源请求。
        self.cpu = cpu_millis

    def __str__(self):
        """
        函数作用：将对象转换为便于日志和调试阅读的字符串。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return 'Resources(CPU: {0} Memory: {1})'.format(self.cpu, self.memory)

    @staticmethod
    def from_str(memory, cpu):
        """
        函数作用：从 Kubernetes 风格资源字符串构造 Resources 对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：memory：内存请求或使用量。；cpu：CPU 请求或使用量。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return Resources(int(cpu.rstrip('m')), parse_size_string(memory))


class FunctionResourceCharacterization:
    """
    类作用：函数单次调用资源画像，保存 CPU、块 I/O、GPU、网络和内存占用。
    核心字段：cpu：CPU 使用量或 CPU 资源请求。；blkio：块设备 I/O 使用量。；gpu：GPU 使用量。；net：网络 I/O 使用量。；ram：内存使用量。。
    核心方法：__init__、__len__、__delitem__、__getitem__、__setitem__。
    """
    # 字段说明：cpu：CPU 使用量或 CPU 资源请求。
    cpu: float
    # 字段说明：blkio：块设备 I/O 使用量。
    blkio: float
    # 字段说明：gpu：GPU 使用量。
    gpu: float
    # 字段说明：net：网络 I/O 使用量。
    net: float
    # 字段说明：ram：内存使用量。
    ram: float

    def __init__(self, cpu: float, blkio: float, gpu: float, net: float, ram: float):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：blkio、cpu、gpu、net、ram。
        参数：cpu：CPU 请求或使用量。；blkio：块设备 I/O 使用量。；gpu：GPU 使用量。；net：网络 I/O 使用量。；ram：内存使用量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.cpu：CPU 使用量或 CPU 资源请求。
        self.cpu = cpu
        # 字段说明：self.blkio：块设备 I/O 使用量。
        self.blkio = blkio
        # 字段说明：self.gpu：GPU 使用量。
        self.gpu = gpu
        # 字段说明：self.net：网络 I/O 使用量。
        self.net = net
        # 字段说明：self.ram：内存使用量。
        self.ram = ram

    def __len__(self):
        """
        函数作用：返回对象内部资源项数量。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return 5

    def __delitem__(self, key):
        """
        函数作用：按键删除内部字段或资源项。
        参数：key：字典或资源表的索引键。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.__delattr__(key)

    def __getitem__(self, key):
        """
        函数作用：按键读取内部字段或资源项。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：key：字典或资源表的索引键。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.__getattribute__(key)

    def __setitem__(self, key, value):
        """
        函数作用：按键更新内部字段或资源项。
        参数：key：字典或资源表的索引键。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.__setattr__(key, value)


class FunctionCharacterization:

    """
    类作用：函数画像聚合对象，把执行时间 Oracle 与资源 Oracle 绑定到同一个函数镜像。
    核心方法：__init__、sample_fet、get_resources_for_node。
    """
    def __init__(self, image: str, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fet_oracle、image、resource_oracle。
        参数：image：容器镜像标识。；fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.image：表示 image，在当前业务流程中作为输入参数、状态字段或计算结果使用。
        self.image = image
        # 字段说明：self.fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。
        self.fet_oracle = fet_oracle
        # 字段说明：self.resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
        self.resource_oracle = resource_oracle

    def sample_fet(self, host: str) -> Optional[float]:
        """
        函数作用：在指定节点上采样函数执行时间。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host：执行函数的目标主机或节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.fet_oracle.sample(host, self.image)

    def get_resources_for_node(self, host: str) -> FunctionResourceCharacterization:
        """
        函数作用：读取函数在指定节点上的资源画像。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host：执行函数的目标主机或节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.resource_oracle.get_resources(host, self.image)


class FunctionImage:
    
    """
    类作用：函数镜像标识对象，对应某个函数在特定平台或架构上的容器镜像。
    核心字段：image：表示 image，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    核心方法：__init__。
    """
    # 字段说明：image：表示 image，在当前业务流程中作为输入参数、状态字段或计算结果使用。
    image: str

    def __init__(self, image: str):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：image。
        参数：image：容器镜像标识。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.image：表示 image，在当前业务流程中作为输入参数、状态字段或计算结果使用。
        self.image = image


class DeploymentRanking:
    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    """
    类作用：部署镜像偏好排序，用于在多个 FunctionContainer 中选择优先部署的镜像。
    核心字段：images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。；function_factor：函数层面的偏好因子，用于部署排序或调度打分。。
    核心方法：__init__、set_first、get_first。
    """
    # 字段说明：images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
    images: List[str]

    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    # 业务说明：这里与副本放置或调度决策有关。
    # 字段说明：function_factor：函数层面的偏好因子，用于部署排序或调度打分。
    function_factor: Dict[str, float]

    def __init__(self, images: List[str], function_factor: Dict[str, float] = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：function_factor、images。
        参数：images：容器镜像集合。；function_factor：函数层面的偏好因子，用于部署排序或调度打分。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
        self.images = images
        # 字段说明：self.function_factor：函数层面的偏好因子，用于部署排序或调度打分。
        self.function_factor = function_factor if function_factor is not None else {image: 1 for image in images}

    def set_first(self, image: str):
        """
        函数作用：更新对象内部状态或实验配置。
        关键流程：
        - 写入对象字段：images。
        参数：image：容器镜像标识。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        index = self.images.index(image)
        updated = self.images[:index] + self.images[index + 1:]
        # 字段说明：self.images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
        self.images = [image] + updated

    def get_first(self):
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.images[0]


class ResourceConfiguration(abc.ABC):

    """
    类作用：资源配置抽象接口，约束子类返回调度所需的资源请求。
    继承关系：abc.ABC。
    核心方法：get_resource_requirements。
    """
    # 方法说明：函数作用：返回调度所需的资源请求。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def get_resource_requirements(self) -> Dict: ...


class KubernetesResourceConfiguration(ResourceConfiguration):
    """
    类作用：Kubernetes 资源请求配置，实现从 CPU/Memory 字符串到 Resources 对象的转换。
    继承关系：ResourceConfiguration。
    核心字段：requests：Kubernetes 风格资源请求集合。。
    核心方法：__init__、get_resource_requirements、create_from_str。
    """
    # 字段说明：requests：Kubernetes 风格资源请求集合。
    requests: Resources

    def __init__(self, requests: Resources = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：requests。
        参数：requests：Kubernetes 风格资源请求集合。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.requests：Kubernetes 风格资源请求集合。
        self.requests = requests if requests is not None else Resources()

    def get_resource_requirements(self) -> Dict:
        """
        函数作用：返回调度所需的资源请求。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return {
            'cpu': self.requests.cpu,
            'memory': self.requests.memory
        }

    @staticmethod
    def create_from_str(cpu: str, memory: str):
        """
        函数作用：从 CPU 和内存字符串创建 KubernetesResourceConfiguration。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：cpu：CPU 请求或使用量。；memory：内存请求或使用量。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return KubernetesResourceConfiguration(Resources.from_str(memory, cpu))


class Function:
    """
    类作用：函数定义对象，描述可被调用的业务函数名称、可用镜像和标签。
    核心字段：name：业务对象名称，通常用于函数、节点、镜像或实验标识。；fn_images：函数可用镜像列表。；labels：调度标签或业务标签，用于节点能力匹配。。
    核心方法：__init__、get_image。
    """
    # 字段说明：name：业务对象名称，通常用于函数、节点、镜像或实验标识。
    name: str
    # 字段说明：fn_images：函数可用镜像列表。
    fn_images: List[FunctionImage]
    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    # 字段说明：labels：调度标签或业务标签，用于节点能力匹配。
    labels: Dict[str, str]

    def __init__(self, name: str, fn_images: List[FunctionImage], labels: Dict[str, str] = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn_images、labels、name。
        参数：name：对象名称。；fn_images：函数可用镜像列表。；labels：调度标签或业务标签，用于节点能力匹配。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn_images：函数可用镜像列表。
        self.fn_images = fn_images
        # 字段说明：self.name：业务对象名称，通常用于函数、节点、镜像或实验标识。
        self.name = name
        # 字段说明：self.labels：调度标签或业务标签，用于节点能力匹配。
        self.labels = labels if labels is not None else {}

    def get_image(self, image: str) -> Optional[FunctionImage]:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：image：容器镜像标识。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        for fn_image in self.fn_images:
            if fn_image.image == image:
                return fn_image
        return None


class FunctionContainer:
    """
    类作用：函数容器规格，绑定函数镜像、资源请求和标签，是创建副本的模板。
    核心字段：fn_image：当前容器规格绑定的函数镜像。；resource_config：函数容器资源请求配置。；labels：调度标签或业务标签，用于节点能力匹配。。
    核心方法：__init__、image、get_resource_requirements。
    """
    # 字段说明：fn_image：当前容器规格绑定的函数镜像。
    fn_image: FunctionImage
    # 字段说明：resource_config：函数容器资源请求配置。
    resource_config: ResourceConfiguration
    # 字段说明：labels：调度标签或业务标签，用于节点能力匹配。
    labels: Dict[str, str]

    def __init__(self, fn_image: FunctionImage, resource_config: ResourceConfiguration = None,
                 labels: Dict[str, str] = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn_image、labels、resource_config。
        参数：fn_image：当前容器规格绑定的函数镜像。；resource_config：函数容器资源请求配置。；labels：调度标签或业务标签，用于节点能力匹配。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn_image：当前容器规格绑定的函数镜像。
        self.fn_image = fn_image
        # 字段说明：self.resource_config：函数容器资源请求配置。
        self.resource_config = resource_config if resource_config is not None else KubernetesResourceConfiguration()
        # 字段说明：self.labels：调度标签或业务标签，用于节点能力匹配。
        self.labels = labels if labels is not None else {}

    @property
    def image(self):
        """
        函数作用：返回函数副本或容器对应的镜像标识。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.fn_image.image

    def get_resource_requirements(self):
        """
        函数作用：返回调度所需的资源请求。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.resource_config.get_resource_requirements()


class ScalingConfiguration:
    """
    类作用：函数伸缩配置，保存最小/最大副本数、RPS 阈值、队列阈值和 scale-to-zero 参数。
    核心字段：scale_min：函数最小副本数。；scale_max：函数最大副本数。；scale_factor：每次伸缩调整的副本步长。；scale_zero：是否允许函数缩容到 0。；rps_threshold：触发请求数伸缩的 RPS 阈值。；alert_window：伸缩判断使用的观测时间窗口。；rps_threshold_duration：RPS 超阈值需要持续的时间。；target_average_utilization：HPA 目标平均资源利用率。 等。
    """
    # 字段说明：scale_min：函数最小副本数。
    scale_min: int = 1
    # 字段说明：scale_max：函数最大副本数。
    scale_max: int = 20
    # 字段说明：scale_factor：每次伸缩调整的副本步长。
    scale_factor: int = 1
    # 字段说明：scale_zero：是否允许函数缩容到 0。
    scale_zero: bool = False

    # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
    # 字段说明：rps_threshold：触发请求数伸缩的 RPS 阈值。
    rps_threshold: int = 20

    
    # 字段说明：alert_window：伸缩判断使用的观测时间窗口。
    alert_window: int = 50  # 待办：这里保留了后续完善点，需要结合实验目标继续细化。

    
    # 字段说明：rps_threshold_duration：RPS 超阈值需要持续的时间。
    rps_threshold_duration: int = 10

    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    # 字段说明：target_average_utilization：HPA 目标平均资源利用率。
    target_average_utilization: float = 0.5

    # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
    # 字段说明：target_average_rps：目标平均每副本 RPS。
    target_average_rps: int = 200

    # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
    # 字段说明：target_queue_length：目标队列长度。
    target_queue_length: int = 75

    # 字段说明：target_average_rps_threshold：平均 RPS 触发阈值。
    target_average_rps_threshold = 0.1


class FunctionDeployment:
    """
    类作用：函数部署对象，把 Function、容器规格、伸缩策略和镜像排序组合成平台可部署单元。
    核心字段：fn：函数定义对象，保存函数名称、镜像集合和标签。；fn_containers：函数容器规格列表，表示一个部署可选的运行镜像/资源组合。；scaling_config：函数伸缩策略配置。；ranking：镜像/容器部署优先级排序。。
    核心方法：__init__、get_selected_service、get_services、get_containers、get_container、name。
    """
    # 字段说明：fn：函数定义对象，保存函数名称、镜像集合和标签。
    fn: Function
    # 字段说明：fn_containers：函数容器规格列表，表示一个部署可选的运行镜像/资源组合。
    fn_containers: List[FunctionContainer]
    # 字段说明：scaling_config：函数伸缩策略配置。
    scaling_config: ScalingConfiguration
    
    # 字段说明：ranking：镜像/容器部署优先级排序。
    ranking: DeploymentRanking

    def __init__(self, fn: Function, fn_containers: List[FunctionContainer], scaling_config: ScalingConfiguration,
                 deployment_ranking: DeploymentRanking = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn、fn_containers、ranking、scaling_config。
        参数：fn：函数定义对象或函数名。；fn_containers：函数容器规格列表，表示一个部署可选的运行镜像/资源组合。；scaling_config：函数伸缩策略配置。；deployment_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn：函数定义对象，保存函数名称、镜像集合和标签。
        self.fn = fn
        # 字段说明：self.fn_containers：函数容器规格列表，表示一个部署可选的运行镜像/资源组合。
        self.fn_containers = fn_containers
        # 字段说明：self.scaling_config：函数伸缩策略配置。
        self.scaling_config = scaling_config
        if deployment_ranking is None:
            # 字段说明：self.ranking：镜像/容器部署优先级排序。
            self.ranking = DeploymentRanking([x.image for x in self.fn.fn_images])
        else:
            self.ranking = deployment_ranking

    def get_selected_service(self):
        """
        函数作用：根据部署排序选择当前优先使用的函数容器规格。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.fn.get_image(self.ranking.get_first())

    def get_services(self):
        """
        函数作用：返回该部署包含的所有函数容器规格。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return list(map(lambda image: self.fn.get_image(image), self.ranking.images))

    def get_containers(self):
        """
        函数作用：返回该部署可用的容器规格列表。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return [self.get_container(image) for image in self.ranking.images]

    def get_container(self, image: str) -> Optional[FunctionContainer]:
        """
        函数作用：根据镜像标识查找对应函数容器规格。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：image：容器镜像标识。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        for fn_image in self.fn_containers:
            if fn_image.image == image:
                return fn_image
        return None

    @property
    def name(self):
        """
        函数作用：返回对象在业务域中的稳定名称。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.fn.name


class FunctionReplica:
    """
    类作用：函数运行副本，记录所属函数、容器、所在节点、Pod、生命周期状态和函数模拟器。
    核心字段：function：函数定义或函数名称，表示当前副本/请求所属业务函数。；container：函数容器规格，决定副本镜像和资源请求。；node：函数副本被调度到的目标节点。；pod：调度器使用的 Pod 视图。；state：函数副本生命周期状态。；simulator：函数副本绑定的生命周期模拟器。。
    核心方法：fn_name、image。
    """
    # 字段说明：function：函数定义或函数名称，表示当前副本/请求所属业务函数。
    function: FunctionDeployment
    # 字段说明：container：函数容器规格，决定副本镜像和资源请求。
    container: FunctionContainer
    # 字段说明：node：函数副本被调度到的目标节点。
    node: NodeState
    # 字段说明：pod：调度器使用的 Pod 视图。
    pod: Pod
    # 字段说明：state：函数副本生命周期状态。
    state: FunctionState = FunctionState.CONCEIVED

    # 字段说明：simulator：函数副本绑定的生命周期模拟器。
    simulator: 'FunctionSimulator' = None

    @property
    def fn_name(self):
        """
        函数作用：返回副本所属函数的名称。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.function.name

    @property
    def image(self):
        """
        函数作用：返回函数副本或容器对应的镜像标识。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.container.image


class FunctionRequest:
    """
    类作用：函数调用请求，保存请求 ID、目标函数名和请求体大小，用于负载生成与指标关联。
    核心字段：request_id：函数调用请求的唯一编号。；name：业务对象名称，通常用于函数、节点、镜像或实验标识。；size：请求数据大小，影响网络传输耗时。；id_generator：请求 ID 自增生成器。。
    核心方法：__init__、__str__、__repr__。
    """
    # 字段说明：request_id：函数调用请求的唯一编号。
    request_id: int
    # 字段说明：name：业务对象名称，通常用于函数、节点、镜像或实验标识。
    name: str
    # 字段说明：size：请求数据大小，影响网络传输耗时。
    size: float = None

    # 字段说明：id_generator：请求 ID 自增生成器。
    id_generator = counter()

    def __init__(self, name, size=None) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：name、request_id、size。
        参数：name：对象名称。；size：请求数据大小，影响网络传输耗时。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.name：业务对象名称，通常用于函数、节点、镜像或实验标识。
        self.name = name
        # 字段说明：self.size：请求数据大小，影响网络传输耗时。
        self.size = size
        # 字段说明：self.request_id：函数调用请求的唯一编号。
        self.request_id = next(self.id_generator)

    def __str__(self) -> str:
        """
        函数作用：将对象转换为便于日志和调试阅读的字符串。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return 'FunctionRequest(%d, %s, %s)' % (self.request_id, self.name, self.size)

    def __repr__(self):
        """
        函数作用：返回对象的调试字符串表示，便于交互式查看。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.__str__()


class FunctionResponse(NamedTuple):
    """
    类作用：函数调用响应记录，保存请求 ID、状态码、排队时间、执行时间和执行节点。
    继承关系：NamedTuple。
    核心字段：request_id：函数调用请求的唯一编号。；code：函数响应状态码。；t_wait：请求等待可用副本或排队的耗时。；t_exec：函数主体执行耗时。；node：函数副本被调度到的目标节点。。
    """
    # 字段说明：request_id：函数调用请求的唯一编号。
    request_id: int
    # 字段说明：code：函数响应状态码。
    code: int
    # 字段说明：t_wait：请求等待可用副本或排队的耗时。
    t_wait: float = 0
    # 字段说明：t_exec：函数主体执行耗时。
    t_exec: float = 0
    # 字段说明：node：函数副本被调度到的目标节点。
    node: str = None


class FaasSystem(abc.ABC):

    """
    类作用：FaaS 平台抽象接口，定义部署、调用、删除、扩缩容和副本发现等平台操作。
    继承关系：abc.ABC。
    核心方法：deploy、invoke、remove、get_deployments、get_function_index、get_replicas、scale_down、scale_up、discover、suspend、poll_available_replica。
    """
    @abc.abstractmethod
    # 方法说明：函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
    # 方法说明：参数：fn：函数定义对象或函数名。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def deploy(self, fn: FunctionDeployment): ...

    @abc.abstractmethod
    # 方法说明：函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
    # 方法说明：参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def invoke(self, request: FunctionRequest): ...

    @abc.abstractmethod
    # 方法说明：函数作用：删除函数部署并清理其所有运行副本。
    # 方法说明：参数：fn：函数定义对象或函数名。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def remove(self, fn: FunctionDeployment): ...

    @abc.abstractmethod
    # 方法说明：函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def get_deployments(self) -> List[FunctionDeployment]: ...

    @abc.abstractmethod
    # 方法说明：函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def get_function_index(self) -> Dict[str, FunctionContainer]: ...

    @abc.abstractmethod
    # 方法说明：函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    # 方法说明：参数：fn_name：目标函数名称。；state：副本生命周期状态过滤条件。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def get_replicas(self, fn_name: str, state=None) -> List[FunctionReplica]: ...

    @abc.abstractmethod
    # 方法说明：函数作用：缩减函数副本数，选择待删除副本并执行生命周期清理。
    # 方法说明：参数：function_name：目标函数名称。；remove：需要移除的副本数量或副本列表。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def scale_down(self, function_name: str, remove: int): ...

    @abc.abstractmethod
    # 方法说明：函数作用：增加函数副本数，在伸缩上限内创建并调度新副本。
    # 方法说明：参数：function_name：目标函数名称。；replicas：副本数量或副本列表。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def scale_up(self, function_name: str, replicas: int): ...

    @abc.abstractmethod
    # 方法说明：函数作用：查询指定函数当前可见的运行副本列表。
    # 方法说明：参数：function：目标函数定义或函数名。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def discover(self, function: FunctionContainer) -> List[FunctionReplica]: ...

    @abc.abstractmethod
    # 方法说明：函数作用：挂起函数部署，使相关副本不再接收请求。
    # 方法说明：参数：function_name：目标函数名称。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def suspend(self, function_name: str): ...

    @abc.abstractmethod
    # 方法说明：函数作用：周期性等待目标函数出现 RUNNING 副本。
    # 方法说明：参数：fn：函数定义对象或函数名。；interval：轮询或采样间隔。。
    # 方法说明：返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    def poll_available_replica(self, fn: str, interval=0.5): ...


class LoadBalancer:
    """
    类作用：负载均衡器基类，负责从可运行副本中选择一个处理函数请求。
    核心字段：env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。；replicas：函数副本列表或副本数量，表示平台当前/目标运行实例规模。。
    核心方法：__init__、get_running_replicas、next_replica。
    """
    # 字段说明：env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
    env: Environment
    # 字段说明：replicas：函数副本列表或副本数量，表示平台当前/目标运行实例规模。
    replicas: Dict[str, List[FunctionReplica]]

    def __init__(self, env, replicas) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：env、replicas。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replicas：副本数量或副本列表。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.replicas：函数副本列表或副本数量，表示平台当前/目标运行实例规模。
        self.replicas = replicas

    def get_running_replicas(self, function: str):
        """
        函数作用：过滤出指定函数当前处于 RUNNING 状态的副本。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：function：目标函数定义或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return [replica for replica in self.replicas[function] if replica.state == FunctionState.RUNNING]

    def next_replica(self, request: FunctionRequest) -> FunctionReplica:
        """
        函数作用：根据负载均衡策略为请求选择下一 个可用副本。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError


class RoundRobinLoadBalancer(LoadBalancer):

    """
    类作用：轮询负载均衡器，按函数维度维护迭代器并顺序选择运行中副本。
    继承关系：LoadBalancer。
    核心方法：__init__、next_replica。
    """
    def __init__(self, env, replicas) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：counters。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replicas：副本数量或副本列表。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__(env, replicas)
        # 字段说明：self.counters：多维计数器集合，用于记录设备和属性分布。
        self.counters = defaultdict(lambda: 0)

    def next_replica(self, request: FunctionRequest) -> FunctionReplica:
        """
        函数作用：根据负载均衡策略为请求选择下一 个可用副本。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        replicas = self.get_running_replicas(request.name)
        i = self.counters[request.name] % len(replicas)
        self.counters[request.name] = (i + 1) % len(replicas)

        replica = replicas[i]

        return replica


class FunctionSimulator(abc.ABC):

    """
    类作用：函数生命周期模拟器抽象，约束 deploy、startup、setup、invoke、teardown 五个阶段。
    继承关系：abc.ABC。
    核心方法：deploy、startup、setup、invoke、teardown。
    """
    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟副本启动阶段耗时，通常对应容器启动或运行时初始化。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟函数副本关闭阶段，释放资源并完成生命周期收尾。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)


class SimulatorFactory:

    """
    类作用：函数模拟器工厂，按函数定义为每个新副本创建对应的 FunctionSimulator。
    核心方法：create。
    """
    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError
