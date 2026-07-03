"""
文件作用：容器镜像仓库和镜像拉取模拟，实现镜像元数据登记、按架构查找镜像，以及通过网络流下载镜像大小。
主要类：ImageProperties、ContainerRegistry。
主要函数：split_image_name、pull。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

from collections import defaultdict
from typing import List, Tuple, NamedTuple, Dict

from sim.core import Node, Environment
from sim.net import SafeFlow
from sim.topology import DockerRegistry


class ImageProperties(NamedTuple):
    """
    类作用：容器镜像元数据，保存镜像名、大小、标签和 CPU 架构。
    继承关系：NamedTuple。
    核心字段：name：业务对象名称，通常用于函数、节点、镜像或实验标识。；size：请求数据大小，影响网络传输耗时。；tag：表示 tag，在当前业务流程中作为输入参数、状态字段或计算结果使用。；arch：CPU 架构属性，例如 x86、arm32、aarch64。。
    """
    # 字段说明：name：业务对象名称，通常用于函数、节点、镜像或实验标识。
    name: str
    # 字段说明：size：请求数据大小，影响网络传输耗时。
    size: int
    # 字段说明：tag：表示 tag，在当前业务流程中作为输入参数、状态字段或计算结果使用。
    tag: str = 'latest'
    # 字段说明：arch：CPU 架构属性，例如 x86、arm32、aarch64。
    arch: str = None


class ContainerRegistry:
    """
    类作用：容器镜像仓库，支持登记镜像和按名称/标签/架构查找镜像。
    核心字段：images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。。
    核心方法：__init__、put、put_all、find。
    """

    
    # 字段说明：images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
    images: Dict[str, Dict[str, List[ImageProperties]]]

    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：images。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
        self.images = defaultdict(lambda: defaultdict(list))

    def put(self, image: ImageProperties):
        """
        函数作用：向内部索引或仓库写入一个对象。
        参数：image：容器镜像标识。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.images[image.name][image.tag].append(image)

    def put_all(self, images: List[ImageProperties]):
        """
        函数作用：批量写入多个对象到内部索引或仓库。
        参数：images：容器镜像集合。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        for image in images:
            self.put(image)

    def find(self, image: str, arch=None) -> List[ImageProperties]:
        """
        函数作用：按条件查找匹配的对象或镜像。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：image：容器镜像标识。；arch：CPU 架构属性，例如 x86、arm32、aarch64。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        repository, tag = split_image_name(image)

        images = self.images[repository][tag]

        if arch:
            images = [image for image in images if image.arch == arch or image.arch is None]

        return images


def split_image_name(image: str) -> Tuple[str, str]:
    """
    函数作用：处理 split、image、name 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：image：容器镜像标识。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    parts = image.split(':', maxsplit=1)

    if len(parts) == 1:
        return parts[0], 'latest'

    return parts[0], parts[1]


def pull(env: Environment, image_str: str, node: Node):
    """
    函数作用：模拟从容器仓库拉取镜像，并把网络传输耗时纳入仿真时间。
    关键流程：
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；image_str：表示 image、str，在当前业务流程中作为输入参数、状态字段或计算结果使用。；node：候选或目标节点。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    started = env.now
    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    # 业务说明：这里处理镜像或数据下载，相关耗时会进入仿真时间。

    # 业务说明：这里处理节点、拓扑或网络连接相关状态。
    images = env.container_registry.find(image_str, arch=node.arch)
    if not images:
        raise ValueError('image not in registry: %s arch=%s' % (image_str, node.arch))
    image = images[0]

    node_state = env.get_node_state(node.name)
    if node_state:
        if image in node_state.docker_images:
            return
        else:
            node_state.docker_images.add(image)

    size = image.size

    if size <= 0:
        return

    # 修正提示：这里标记了原实现中需要进一步确认的边界。
    # 业务说明：这里处理节点、拓扑或网络连接相关状态。
    
    

    route = env.topology.route(DockerRegistry, node)
    flow = SafeFlow(env, size, route)

    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield flow.start()

    
    # 业务说明：这里处理镜像或数据下载，相关耗时会进入仿真时间。
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'docker_pull')
