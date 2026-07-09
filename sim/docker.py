"""
容器镜像仓库与镜像拉取模拟。

ContainerRegistry 维护镜像名称、tag、架构和大小的索引；pull() 根据目标节点架构查找镜像，并通过网络 SafeFlow 把镜像传输耗时纳入仿真时间。
"""

from collections import defaultdict
from typing import List, Tuple, NamedTuple, Dict

from sim.core import Node, Environment
from sim.net import SafeFlow
from sim.topology import DockerRegistry


class ImageProperties(NamedTuple):
    """
    容器镜像元数据记录。

    保存镜像名、tag、大小和 CPU 架构，用于容器仓库查找和镜像拉取耗时计算。

    重要字段：
    - name: 业务对象名称，通常是函数名、节点名或实验名称。
    - size: 镜像或请求数据大小，通常以字节为单位。
    - tag: 镜像 tag，不显式指定时通常为 latest。
    - arch: CPU 架构标签，用于判断镜像是否能在目标节点运行。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    name: str
    size: int
    tag: str = 'latest'
    arch: str = None


class ContainerRegistry:
    """
    仿真内的容器镜像仓库。

    按镜像名、tag 和架构索引 ImageProperties，供 Docker pull 模拟过程查找合适镜像。

    重要字段：
    - images: 镜像列表、镜像索引或镜像排序，具体含义取决于所属类。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    
    images: Dict[str, Dict[str, List[ImageProperties]]]

    def __init__(self) -> None:
        """
        初始化 ContainerRegistry 对象。

        主要建立字段：images。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.images = defaultdict(lambda: defaultdict(list))

    def put(self, image: ImageProperties):
        """
        把一个镜像元数据加入仓库索引。

        索引层级为镜像名 -> tag -> ImageProperties 列表。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：ImageProperties。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.images[image.name][image.tag].append(image)

    def put_all(self, images: List[ImageProperties]):
        """
        批量登记镜像元数据。

        逐个调用 put，保持单个写入逻辑一致。

        参数说明：
        - images: 镜像元数据列表或镜像名列表，具体取决于当前函数。 类型标注：List[ImageProperties]。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        for image in images:
            self.put(image)

    def find(self, image: str, arch=None) -> List[ImageProperties]:
        """
        按镜像名、tag 和可选架构查找镜像。

        镜像字符串不带 tag 时默认使用 latest；传入 arch 时会同时接受架构匹配和未声明架构的镜像。

        参数说明：
        - image: 镜像名或 FunctionImage。 类型标注：str。
        - arch: arch 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：返回值类型标注为 List[ImageProperties]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        repository, tag = split_image_name(image)

        images = self.images[repository][tag]

        if arch:
            images = [image for image in images if image.arch == arch or image.arch is None]

        return images


def split_image_name(image: str) -> Tuple[str, str]:
    """
    拆分镜像名和 tag。

    输入不含冒号时返回 latest 作为默认 tag。

    参数说明：
    - image: 镜像名或 FunctionImage。 类型标注：str。

    返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。
    """
    parts = image.split(':', maxsplit=1)

    if len(parts) == 1:
        return parts[0], 'latest'

    return parts[0], parts[1]


def pull(env: Environment, image_str: str, node: Node):
    """
    模拟一次 Docker 镜像拉取。

    方法按节点架构查找镜像，命中节点缓存时直接返回；未缓存时把镜像加入缓存，并通过 SafeFlow 模拟 registry 到节点的网络传输耗时。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - image_str: 镜像字符串，通常形如 repository:tag。 类型标注：str。
    - node: 目标节点或节点视图。 类型标注：Node。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    started = env.now

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

    
    

    route = env.topology.route(DockerRegistry, node)
    flow = SafeFlow(env, size, route)

    yield flow.start()

    
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'docker_pull')
