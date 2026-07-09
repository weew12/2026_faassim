"""
FaaS 领域模型核心。

本模块定义函数计算平台的核心业务对象：函数、镜像、容器规格、部署、运行副本、请求/响应、资源配置、生命周期状态、负载均衡器、FaaS 系统接口和函数模拟器接口。

阅读建议：先理解 FunctionDeployment、FunctionReplica、FunctionRequest，再看 FaasSystem 与 FunctionSimulator 抽象接口。
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

logger = logging.getLogger(__name__)

Node = EtherNode


def counter(start: int = 1):
    """
    生成从 start 开始递增的整数序列。

    FunctionRequest 使用该生成器分配稳定递增的 request_id。

    参数说明：
    - start: start 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：int。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    n = start
    while True:
        yield n
        n += 1


class FunctionState(enum.Enum):
    """
    函数副本生命周期状态枚举。

    CONCEIVED 表示刚创建；STARTING 表示正在拉镜像/启动/setup；RUNNING 表示可接收请求；SUSPENDED 表示已挂起。

    重要字段：
    - CONCEIVED: 副本刚被创建，还没有完成调度和启动。
    - STARTING: 副本正在启动，包括镜像拉取、deploy、startup 和 setup。
    - RUNNING: 副本已经可处理请求。
    - SUSPENDED: 副本已挂起，不应再被负载均衡器选中。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    CONCEIVED = 1
    STARTING = 2
    RUNNING = 3
    SUSPENDED = 4


class Resources:
    """
    Kubernetes 风格资源请求。

    保存 CPU 毫核和内存字节数，并提供从字符串配置构造对象的辅助方法。

    重要字段：
    - memory: 内存大小或内存资源请求，通常以字节为单位。
    - cpu: CPU 资源请求或 CPU 占用，通常使用 Kubernetes 毫核单位。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    memory: int
    cpu: int

    def __init__(self, cpu_millis: int = 1 * 1000, memory: int = 1 * 1024 * 1024):
        """
        初始化 Resources 对象。

        主要建立字段：memory、cpu。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - cpu_millis: cpu_millis 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：int。
        - memory: memory 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：int。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.memory = memory
        self.cpu = cpu_millis

    def __str__(self):
        """
        返回适合日志和用户阅读的字符串表示。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return 'Resources(CPU: {0} Memory: {1})'.format(self.cpu, self.memory)

    @staticmethod
    def from_str(memory, cpu):
        """
        从 Kubernetes 风格字符串创建资源请求。

        cpu 使用类似 500m 的毫核格式，memory 使用 ether.parse_size_string 支持的容量字符串。

        参数说明：
        - memory: memory 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - cpu: cpu 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return Resources(int(cpu.rstrip('m')), parse_size_string(memory))


class FunctionResourceCharacterization:
    """
    函数资源画像。

    保存一次函数执行的 CPU、块 I/O、GPU、网络和内存占用，并支持字典风格访问。

    重要字段：
    - cpu: CPU 资源请求或 CPU 占用，通常使用 Kubernetes 毫核单位。
    - blkio: 块设备 I/O 占用估计。
    - gpu: GPU 占用估计。
    - net: 网络资源占用估计。
    - ram: 内存占用估计。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    cpu: float
    blkio: float
    gpu: float
    net: float
    ram: float

    def __init__(self, cpu: float, blkio: float, gpu: float, net: float, ram: float):
        """
        初始化函数资源画像。

        保存一次函数执行在 CPU、块 I/O、GPU、网络和内存五类资源上的占用估计。

        参数说明：
        - cpu: cpu 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。
        - blkio: blkio 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。
        - gpu: gpu 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。
        - net: net 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。
        - ram: ram 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.cpu = cpu
        self.blkio = blkio
        self.gpu = gpu
        self.net = net
        self.ram = ram

    def __len__(self):
        """
        返回资源画像包含的资源维度数量。

        当前固定为 cpu、blkio、gpu、net、ram 五个维度。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return 5

    def __delitem__(self, key):
        """
        按资源名删除画像字段。

        该方法让资源画像可以像字典一样执行 del characterization["cpu"]。

        参数说明：
        - key: key 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.__delattr__(key)

    def __getitem__(self, key):
        """
        按资源名读取画像字段。

        例如 characterization["cpu"] 等价于读取 characterization.cpu。

        参数说明：
        - key: key 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.__getattribute__(key)

    def __setitem__(self, key, value):
        """
        按资源名写入画像字段。

        例如 characterization["ram"] = value 等价于设置 characterization.ram。

        参数说明：
        - key: key 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - value: 要记录或累加的数值。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.__setattr__(key, value)


class FunctionCharacterization:

    """
    函数画像聚合对象。

    把执行时间 Oracle 和资源 Oracle 绑定到同一个镜像，提供按节点采样执行时间和资源占用的入口。

    重要字段：
    - image: 容器镜像字符串，例如 repository:tag。
    - fet_oracle: 函数执行时间 Oracle，用于按主机和镜像采样执行耗时。
    - resource_oracle: 资源画像 Oracle，用于按主机和镜像读取 CPU、内存、网络等资源占用。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, image: str, fet_oracle: FetOracle, resource_oracle: ResourceOracle):
        """
        初始化 FunctionCharacterization 对象。

        主要建立字段：image、fet_oracle、resource_oracle。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。
        - fet_oracle: fet_oracle 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：FetOracle。
        - resource_oracle: 资源 Oracle，用于查询函数在不同节点上的资源画像。 类型标注：ResourceOracle。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.image = image
        self.fet_oracle = fet_oracle
        self.resource_oracle = resource_oracle

    def sample_fet(self, host: str) -> Optional[float]:
        """
        按主机名和镜像从执行时间 Oracle 采样函数执行时间。

        参数说明：
        - host: 主机或节点名称。 类型标注：str。

        返回说明：返回值类型标注为 Optional[float]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.fet_oracle.sample(host, self.image)

    def get_resources_for_node(self, host: str) -> FunctionResourceCharacterization:
        """
        读取 resources_for_node 相关状态。

        该方法不推进仿真时间，只根据当前索引、缓存或对象字段返回结果。调用方需要处理返回 None 或空列表的情况。

        参数说明：
        - host: 主机或节点名称。 类型标注：str。

        返回说明：返回值类型标注为 FunctionResourceCharacterization，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.resource_oracle.get_resources(host, self.image)


class FunctionImage:
    
    """
    函数镜像标识。

    包装镜像字符串，使函数定义可以持有多个可选镜像。

    重要字段：
    - image: 容器镜像字符串，例如 repository:tag。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    image: str

    def __init__(self, image: str):
        """
        初始化 FunctionImage 对象。

        主要建立字段：image。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.image = image


class DeploymentRanking:
    """
    部署镜像优先级排序。

    保存函数可选镜像的偏好顺序，并可把某个镜像移动到首位。

    重要字段：
    - images: 镜像列表、镜像索引或镜像排序，具体含义取决于所属类。
    - function_factor: 镜像或服务的部署比例权重，用于限制不同服务的副本分布。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    images: List[str]

    function_factor: Dict[str, float]

    def __init__(self, images: List[str], function_factor: Dict[str, float] = None):
        """
        初始化 DeploymentRanking 对象。

        主要建立字段：images、function_factor。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - images: 镜像元数据列表或镜像名列表，具体取决于当前函数。 类型标注：List[str]。
        - function_factor: 镜像部署比例权重。 类型标注：Dict[str, float]。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.images = images
        self.function_factor = function_factor if function_factor is not None else {image: 1 for image in images}

    def set_first(self, image: str):
        """
        把指定镜像移动到排序第一位。

        部署扩容时会优先使用排名靠前的镜像，因此该方法可用于动态调整服务选择偏好。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        index = self.images.index(image)
        updated = self.images[:index] + self.images[index + 1:]
        self.images = [image] + updated

    def get_first(self):
        """
        返回当前排序中优先级最高的镜像。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.images[0]


class ResourceConfiguration(abc.ABC):

    """
    资源配置接口。

    子类需要返回调度器可理解的资源请求字典。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def get_resource_requirements(self) -> Dict:
        """
        抽象接口方法：get_resource_requirements。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...


class KubernetesResourceConfiguration(ResourceConfiguration):
    """
    Kubernetes 资源配置实现。

    把 Resources 对象转换为 cpu/memory 字典，并支持从字符串创建配置。

    重要字段：
    - requests: Kubernetes 风格资源请求对象，包含 CPU 和内存需求。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    requests: Resources

    def __init__(self, requests: Resources = None):
        """
        初始化 KubernetesResourceConfiguration 对象。

        主要建立字段：requests。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - requests: requests 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：Resources。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.requests = requests if requests is not None else Resources()

    def get_resource_requirements(self) -> Dict:
        """
        返回调度器使用的资源请求字典。

        字典包含 cpu 毫核和 memory 字节数两个键。

        返回说明：返回值类型标注为 Dict，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return {
            'cpu': self.requests.cpu,
            'memory': self.requests.memory
        }

    @staticmethod
    def create_from_str(cpu: str, memory: str):
        """
        从字符串形式的 CPU 和内存配置创建 KubernetesResourceConfiguration。

        参数说明：
        - cpu: cpu 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：str。
        - memory: memory 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：str。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return KubernetesResourceConfiguration(Resources.from_str(memory, cpu))


class Function:
    """
    函数定义。

    保存函数名、可选镜像和标签，是 FunctionDeployment 的业务基础。

    重要字段：
    - name: 业务对象名称，通常是函数名、节点名或实验名称。
    - fn_images: 函数可选镜像列表，一个函数可对应多个不同架构或实现的镜像。
    - labels: 标签字典，调度器或业务逻辑可通过标签表达约束和元数据。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    name: str
    fn_images: List[FunctionImage]
    labels: Dict[str, str]

    def __init__(self, name: str, fn_images: List[FunctionImage], labels: Dict[str, str] = None):
        """
        初始化 Function 对象。

        主要建立字段：fn_images、name、labels。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：str。
        - fn_images: 函数可选镜像列表。 类型标注：List[FunctionImage]。
        - labels: labels 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：Dict[str, str]。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.fn_images = fn_images
        self.name = name
        self.labels = labels if labels is not None else {}

    def get_image(self, image: str) -> Optional[FunctionImage]:
        """
        按镜像名查找函数支持的 FunctionImage。

        没有匹配镜像时返回 None。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：返回值类型标注为 Optional[FunctionImage]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        for fn_image in self.fn_images:
            if fn_image.image == image:
                return fn_image
        return None


class FunctionContainer:
    """
    函数容器规格。

    绑定函数镜像、资源请求和标签，是创建 FunctionReplica 的模板。

    重要字段：
    - fn_image: 当前容器绑定的函数镜像对象。
    - resource_config: 容器资源配置对象，负责生成调度器可理解的资源请求字典。
    - labels: 标签字典，调度器或业务逻辑可通过标签表达约束和元数据。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    fn_image: FunctionImage
    resource_config: ResourceConfiguration
    labels: Dict[str, str]

    def __init__(self, fn_image: FunctionImage, resource_config: ResourceConfiguration = None,
                 labels: Dict[str, str] = None):
        """
        初始化 FunctionContainer 对象。

        主要建立字段：fn_image、resource_config、labels。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - fn_image: 函数镜像对象。 类型标注：FunctionImage。
        - resource_config: 容器资源配置。 类型标注：ResourceConfiguration。
        - labels: labels 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：Dict[str, str]。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.fn_image = fn_image
        self.resource_config = resource_config if resource_config is not None else KubernetesResourceConfiguration()
        self.labels = labels if labels is not None else {}

    @property
    def image(self):
        """
        返回容器绑定的镜像字符串。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.fn_image.image

    def get_resource_requirements(self):
        """
        返回该容器的资源需求。

        实际格式由 resource_config 决定，默认是 Kubernetes 风格的 cpu/memory 字典。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.resource_config.get_resource_requirements()


class ScalingConfiguration:
    """
    函数伸缩策略配置。

    保存最小/最大副本数、伸缩步长、scale-to-zero、RPS 阈值、队列阈值和目标利用率等参数。

    重要字段：
    - scale_min: 函数最小副本数，缩容不能低于该值。
    - scale_max: 函数最大副本数，扩容不能超过该值。
    - scale_factor: 扩缩容步长比例，通常按 scale_max 的百分比计算每次调整数量。
    - scale_zero: 是否允许函数在空闲时缩到 0 个运行副本。
    - rps_threshold: 基于请求数伸缩时使用的 RPS 阈值。
    - alert_window: 伸缩观察窗口长度。
    - rps_threshold_duration: 计算 RPS 阈值时使用的观察周期。
    - target_average_utilization: HPA 目标平均 CPU 利用率。
    - target_average_rps: 平均 RPS 伸缩器希望每个副本承担的目标请求量。
    - target_queue_length: 队列长度伸缩器使用的目标队列长度。
    - target_average_rps_threshold: 平均 RPS 或队列伸缩的容忍比例，避免频繁抖动。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    scale_min: int = 1
    scale_max: int = 20
    scale_factor: int = 1
    scale_zero: bool = False

    rps_threshold: int = 20

    
    alert_window: int = 50  # RPS 伸缩判断的观察窗口长度，单位为仿真时间。

    
    rps_threshold_duration: int = 10

    target_average_utilization: float = 0.5

    target_average_rps: int = 200

    target_queue_length: int = 75

    target_average_rps_threshold = 0.1


class FunctionDeployment:
    """
    函数部署对象。

    组合 Function、容器规格、伸缩配置和镜像排序，表示平台中一个可部署函数。

    重要字段：
    - fn: 函数定义或函数部署对象，表示当前操作针对的业务函数。
    - fn_containers: 函数可部署容器规格列表，包含镜像、资源请求和标签。
    - scaling_config: 函数伸缩配置，包含副本上下限、阈值和 scale-to-zero 设置。
    - ranking: 镜像/服务选择顺序，扩容时按该顺序尝试创建副本。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    fn: Function
    fn_containers: List[FunctionContainer]
    scaling_config: ScalingConfiguration
    
    ranking: DeploymentRanking

    def __init__(self, fn: Function, fn_containers: List[FunctionContainer], scaling_config: ScalingConfiguration,
                 deployment_ranking: DeploymentRanking = None):
        """
        初始化 FunctionDeployment 对象。

        主要建立字段：fn、fn_containers、scaling_config、ranking。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：Function。
        - fn_containers: 函数可部署容器规格列表。 类型标注：List[FunctionContainer]。
        - scaling_config: 函数伸缩配置。 类型标注：ScalingConfiguration。
        - deployment_ranking: 可选的镜像优先级排序配置。 类型标注：DeploymentRanking。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.fn = fn
        self.fn_containers = fn_containers
        self.scaling_config = scaling_config
        if deployment_ranking is None:
            self.ranking = DeploymentRanking([x.image for x in self.fn.fn_images])
        else:
            self.ranking = deployment_ranking

    def get_selected_service(self):
        """
        返回当前排名第一的函数镜像对象。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.fn.get_image(self.ranking.get_first())

    def get_services(self):
        """
        按部署排名返回全部函数镜像对象。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return list(map(lambda image: self.fn.get_image(image), self.ranking.images))

    def get_containers(self):
        """
        按部署排名返回全部容器规格。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return [self.get_container(image) for image in self.ranking.images]

    def get_container(self, image: str) -> Optional[FunctionContainer]:
        """
        按镜像名查找对应的 FunctionContainer。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：返回值类型标注为 Optional[FunctionContainer]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        for fn_image in self.fn_containers:
            if fn_image.image == image:
                return fn_image
        return None

    @property
    def name(self):
        """
        返回部署对应的函数名。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.fn.name


class FunctionReplica:
    """
    函数运行副本。

    记录所属部署、容器规格、目标节点、Skippy Pod、生命周期状态和模拟器。

    重要字段：
    - function: 副本所属 FunctionDeployment。
    - container: 副本实际运行的 FunctionContainer。
    - node: 目标节点、节点状态或节点名，具体含义取决于所属类。
    - pod: Skippy Pod 对象，是调度器看到的最小调度单元。
    - state: 函数副本生命周期状态。
    - simulator: 函数生命周期模拟器，负责 deploy/startup/setup/invoke/teardown 等阶段耗时。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    function: FunctionDeployment
    container: FunctionContainer
    node: NodeState
    pod: Pod
    state: FunctionState = FunctionState.CONCEIVED

    simulator: 'FunctionSimulator' = None

    @property
    def fn_name(self):
        """
        返回副本所属的函数名。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.function.name

    @property
    def image(self):
        """
        返回副本实际运行的容器镜像。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.container.image


class FunctionRequest:
    """
    函数调用请求。

    保存请求 ID、目标函数名和请求数据大小；请求 ID 来自类级递增生成器。

    重要字段：
    - request_id: 请求唯一编号，用于指标记录和节点历史请求关联。
    - name: 业务对象名称，通常是函数名、节点名或实验名称。
    - size: 镜像或请求数据大小，通常以字节为单位。
    - id_generator: 类级请求 ID 生成器，保证每个 FunctionRequest 拿到递增编号。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    request_id: int
    name: str
    size: float = None

    id_generator = counter()

    def __init__(self, name, size=None) -> None:
        """
        初始化 FunctionRequest 对象。

        主要建立字段：name、size、request_id。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - size: size 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.name = name
        self.size = size
        self.request_id = next(self.id_generator)

    def __str__(self) -> str:
        """
        返回适合日志和用户阅读的字符串表示。

        返回说明：返回值类型标注为 str，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return 'FunctionRequest(%d, %s, %s)' % (self.request_id, self.name, self.size)

    def __repr__(self):
        """
        返回适合调试器和交互式环境显示的字符串表示。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.__str__()


class FunctionResponse(NamedTuple):
    """
    函数调用响应记录。

    保存请求 ID、状态码、等待时间、执行时间和节点名称。

    重要字段：
    - request_id: 请求唯一编号，用于指标记录和节点历史请求关联。
    - code: 函数调用响应状态码。
    - t_wait: 请求等待可用副本或 worker token 的时间。
    - t_exec: 函数执行耗时。
    - node: 目标节点、节点状态或节点名，具体含义取决于所属类。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    request_id: int
    code: int
    t_wait: float = 0
    t_exec: float = 0
    node: str = None


class FaasSystem(abc.ABC):

    """
    FaaS 平台抽象接口。

    定义部署、调用、删除、扩缩容、发现副本、挂起和等待可用副本等平台操作。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    @abc.abstractmethod
    def deploy(self, fn: FunctionDeployment):
        """
        抽象接口方法：deploy。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：典型调用路径是 Benchmark.run -> env.faas.deploy -> scale_up -> deploy_replica -> scheduler_queue。
        """
        ...

    @abc.abstractmethod
    def invoke(self, request: FunctionRequest):
        """
        抽象接口方法：invoke。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：典型调用路径是 requestgen.function_trigger -> env.faas.invoke -> simulate_function_invocation -> replica.simulator.invoke。
        """
        ...

    @abc.abstractmethod
    def remove(self, fn: FunctionDeployment):
        """
        抽象接口方法：remove。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def get_deployments(self) -> List[FunctionDeployment]:
        """
        抽象接口方法：get_deployments。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def get_function_index(self) -> Dict[str, FunctionContainer]:
        """
        抽象接口方法：get_function_index。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def get_replicas(self, fn_name: str, state=None) -> List[FunctionReplica]:
        """
        抽象接口方法：get_replicas。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - state: 副本生命周期状态过滤条件。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def scale_down(self, function_name: str, remove: int):
        """
        抽象接口方法：scale_down。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - function_name: 目标函数名。 类型标注：str。
        - remove: 希望减少的副本数量。 类型标注：int。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：缩容会改变副本生命周期状态并调用 teardown，指标中的负数 scale 表示减少副本。
        """
        ...

    @abc.abstractmethod
    def scale_up(self, function_name: str, replicas: int):
        """
        抽象接口方法：scale_up。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - function_name: 目标函数名。 类型标注：str。
        - replicas: 副本数量或副本列表，具体由所在方法决定。 类型标注：int。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：扩容只创建和排队副本，副本能否运行取决于后续调度和启动流程。
        """
        ...

    @abc.abstractmethod
    def discover(self, function: FunctionContainer) -> List[FunctionReplica]:
        """
        抽象接口方法：discover。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - function: 函数名或函数容器，具体由方法签名决定。 类型标注：FunctionContainer。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def suspend(self, function_name: str):
        """
        抽象接口方法：suspend。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - function_name: 目标函数名。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...

    @abc.abstractmethod
    def poll_available_replica(self, fn: str, interval=0.5):
        """
        抽象接口方法：poll_available_replica。

        这里只声明子类必须提供的能力，不包含具体业务实现。阅读运行逻辑时应跳到对应子类查看实际代码。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：str。
        - interval: 轮询或后台循环间隔，单位为仿真时间。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        ...


class LoadBalancer:
    """
    负载均衡器基类。

    持有副本索引，并提供按函数名筛选 RUNNING 副本的通用逻辑。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - replicas: 函数名到副本列表的映射，记录平台当前已创建的副本。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    env: Environment
    replicas: Dict[str, List[FunctionReplica]]

    def __init__(self, env, replicas) -> None:
        """
        初始化 LoadBalancer 对象。

        主要建立字段：env、replicas。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
        - replicas: 副本数量或副本列表，具体由所在方法决定。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.env = env
        self.replicas = replicas

    def get_running_replicas(self, function: str):
        """
        返回指定函数当前处于 RUNNING 状态的副本。

        参数说明：
        - function: 函数名或函数容器，具体由方法签名决定。 类型标注：str。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return [replica for replica in self.replicas[function] if replica.state == FunctionState.RUNNING]

    def next_replica(self, request: FunctionRequest) -> FunctionReplica:
        """
        负载均衡器选择副本的接口。

        基类不实现具体策略，子类需要根据请求和副本状态返回一个 FunctionReplica。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        raise NotImplementedError


class RoundRobinLoadBalancer(LoadBalancer):

    """
    轮询负载均衡器。

    为每个函数维护计数器，在 RUNNING 副本之间循环选择下一 个处理请求的副本。

    重要字段：
    - counters: 轮询计数器，按函数名记录下一次应该选择哪个副本。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, env, replicas) -> None:
        """
        初始化 RoundRobinLoadBalancer 对象。

        主要建立字段：counters。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
        - replicas: 副本数量或副本列表，具体由所在方法决定。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__(env, replicas)
        self.counters = defaultdict(lambda: 0)

    def next_replica(self, request: FunctionRequest) -> FunctionReplica:
        """
        按轮询策略选择下一个副本。

        计数器按函数名独立维护；每次选择后递增并对副本数量取模，保证请求在 RUNNING 副本之间循环分配。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

        返回说明：返回值类型标注为 FunctionReplica，通常作为后续调度、执行、统计或查询流程的输入。
        """
        replicas = self.get_running_replicas(request.name)
        i = self.counters[request.name] % len(replicas)
        self.counters[request.name] = (i + 1) % len(replicas)

        replica = replicas[i]

        return replica


class FunctionSimulator(abc.ABC):

    """
    函数生命周期模拟器接口。

    定义 deploy、startup、setup、invoke、teardown 五个阶段，具体实现通过 SimPy 协程表达耗时。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        SimPy 协程：deploy。

        函数中的 yield/yield from 会把控制权交还给仿真环境；调用方应使用 yield from 等待完成，或使用 env.process(...) 作为后台进程启动。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：典型调用路径是 Benchmark.run -> env.faas.deploy -> scale_up -> deploy_replica -> scheduler_queue。
        """
        yield env.timeout(0)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        函数副本生命周期协程：startup。

        该阶段可能申请资源、释放资源或用 env.timeout(...) 表示耗时。watchdog 和 simulator 会把多个阶段串联成一次完整函数调用。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        yield env.timeout(0)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        函数副本生命周期协程：setup。

        该阶段可能申请资源、释放资源或用 env.timeout(...) 表示耗时。watchdog 和 simulator 会把多个阶段串联成一次完整函数调用。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：setup 通常只准备状态或外部资源，是否推进仿真时间取决于内部是否包含 yield。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        SimPy 协程：invoke。

        函数中的 yield/yield from 会把控制权交还给仿真环境；调用方应使用 yield from 等待完成，或使用 env.process(...) 作为后台进程启动。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：典型调用路径是 requestgen.function_trigger -> env.faas.invoke -> simulate_function_invocation -> replica.simulator.invoke。
        """
        yield env.timeout(0)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        函数副本生命周期协程：teardown。

        该阶段可能申请资源、释放资源或用 env.timeout(...) 表示耗时。watchdog 和 simulator 会把多个阶段串联成一次完整函数调用。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        yield env.timeout(0)


class SimulatorFactory:

    """
    函数模拟器工厂接口。

    FaaS 系统通过它为函数容器创建对应的 FunctionSimulator。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数模拟器工厂接口。

        FaaS 系统在创建副本时调用该方法，为每个副本绑定生命周期模拟器。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionContainer。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        raise NotImplementedError
