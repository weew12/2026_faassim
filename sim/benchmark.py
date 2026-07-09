"""
Benchmark 场景定义与实验启动流程。

Benchmark 描述一次实验如何准备环境：注册镜像、部署函数、启动请求到达进程，并在指定仿真时长内维持工作负载。
DegradationBenchmarkBase 在基础场景上额外挂载节点性能退化模型，用于多租户资源竞争实验。

阅读建议：BenchmarkBase.run 是实验入口，串联镜像注册、函数部署和请求生成。
"""

import logging
import os
from typing import List, Tuple, Dict, Generator

from ether.util import parse_size_string

from ext.raith21 import loader
from sim import docker
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import FunctionDeployment
from sim.requestgen import function_trigger


class Benchmark:
    

    """
    实验场景基类。

    子类通过 setup() 准备环境，通过 run() 启动部署和请求生成。方法通常是 SimPy 生成器，便于与仿真时间对齐。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def setup(self, env: Environment):
        """
        Benchmark 准备阶段接口。

        子类在这里注册镜像、准备数据或修改环境；默认实现为空。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：setup 通常只准备状态或外部资源，是否推进仿真时间取决于内部是否包含 yield。
        """
        pass

    def run(self, env: Environment):
        """
        Benchmark 运行阶段接口。

        默认只等待 0 仿真时间，子类通常在这里部署函数并启动请求到达进程。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        yield env.timeout(0)


class BenchmarkBase(Benchmark):
    """
    通用 Benchmark 实现。

    负责登记镜像、部署函数、等待副本可用、启动请求到达 profile，并在指定 duration 内维持工作负载。

    重要字段：
    - duration: 实验持续时间，Benchmark 会在该时间后停止继续生成请求。
    - images: 镜像列表、镜像索引或镜像排序，具体含义取决于所属类。
    - deployments: 本次实验需要部署的函数部署列表。
    - deployments_per_name: 函数名到 FunctionDeployment 的索引，便于按名称快速找到部署对象。
    - arrival_profiles: 函数名到到达间隔生成器的映射，用于为不同函数提供不同负载。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, images: List[Tuple[str, str, str]], deployments: List[FunctionDeployment],
                 arrival_profiles: Dict[str, Generator], duration: int = None):
        """
        初始化 BenchmarkBase 对象。

        主要建立字段：duration、images、deployments、deployments_per_name、arrival_profiles。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - images: 镜像元数据列表或镜像名列表，具体取决于当前函数。 类型标注：List[Tuple[str, str, str]]。
        - deployments: 函数部署列表，每个元素描述一个需要部署的函数。 类型标注：List[FunctionDeployment]。
        - arrival_profiles: 函数名到请求到达间隔生成器的映射。 类型标注：Dict[str, Generator]。
        - duration: 仿真持续时间或采样持续时间。 类型标注：int。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.duration = duration  
        self.images = images
        self.deployments = deployments
        self.deployments_per_name = self.__create_deployments_per_name()
        self.arrival_profiles = arrival_profiles

    def __create_deployments_per_name(self):
        """
        构造函数名到部署对象的索引。

        该索引用于根据 arrival profile 的函数名快速找到对应 FunctionDeployment。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        deployments_per_name = {}
        for deployment in self.deployments:
            deployments_per_name[deployment.name] = deployment
        return deployments_per_name

    def setup(self, env: Environment):
        """
        注册 Benchmark 所需镜像。

        先执行父类准备逻辑，再把 images 列表写入容器仓库。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：setup 通常只准备状态或外部资源，是否推进仿真时间取决于内部是否包含 yield。
        """
        super().setup(env)
        self.register_images(env)

    def register_images(self, env: Environment):
        """
        把镜像元数据写入容器仓库。

        images 中的大小字符串会转换为字节数，架构信息会保留给后续镜像匹配和拉取模拟使用。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        containers: docker.ContainerRegistry = env.container_registry
        for image, size, arch in self.images:
            containers.put(ImageProperties(image, parse_size_string(size), arch=arch))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logging.info('%s, %s, %s', name, tag, images)

    def run(self, env: Environment):
        """
        执行通用 Benchmark 流程。

        先部署所有函数并等待副本可用，再为每个部署启动请求触发进程；如果设置 duration，则到期后中断请求进程。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        for deployment in self.deployments:
            yield from env.faas.deploy(deployment)
        for deployment in self.deployments:
            # 协程同步：等待子过程完成，保证业务阶段按顺序衔接。
            yield env.process(env.faas.poll_available_replica(deployment.name))

        ps = []
        logging.info('executing requests')
        for deployment in self.deployments:
            try:
                ia_generator = self.arrival_profiles[deployment.name]
                if self.duration is None:
                    p = env.process(function_trigger(env, deployment, ia_generator, max_requests=1000))
                else:
                    p = env.process(function_trigger(env, deployment, ia_generator))
                ps.append(p)
            except KeyError:
                logging.warning('no arrival profile for deployment %s', deployment.name)

        if self.duration is not None:
            env.process(self.wait(env, ps))

        yield from ps

    def wait(self, env, ps):
        """
        等待指定实验时长后中断请求进程。

        该协程用于让有限时长实验在 duration 后停止继续产生请求。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
        - ps: 需要在指定时间后中断的 SimPy 请求生成进程列表。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        yield env.timeout(env.now + self.duration)
        for p in ps:
            p.interrupt('stop')


class DegradationBenchmarkBase(BenchmarkBase):

    """
    带性能退化模型的 Benchmark。

    在普通 Benchmark 初始化后，为节点加载对应退化模型，使后续执行时间估计可以考虑资源竞争。

    重要字段：
    - model_folder: 性能退化模型文件所在目录。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, images: List[Tuple[str, str, str]], deployments: List[FunctionDeployment],
                 arrival_profiles: Dict[str, Generator], duration: int = None, model_folder='./data'):
        """
        初始化 DegradationBenchmarkBase 对象。

        主要建立字段：model_folder。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - images: 镜像元数据列表或镜像名列表，具体取决于当前函数。 类型标注：List[Tuple[str, str, str]]。
        - deployments: 函数部署列表，每个元素描述一个需要部署的函数。 类型标注：List[FunctionDeployment]。
        - arrival_profiles: 函数名到请求到达间隔生成器的映射。 类型标注：Dict[str, Generator]。
        - duration: 仿真持续时间或采样持续时间。 类型标注：int。
        - model_folder: model_folder 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__(images, deployments, arrival_profiles, duration)
        self.model_folder = model_folder

    def setup(self, env: Environment):
        """
        在普通 Benchmark 准备完成后加载性能退化模型。

        模型会挂载到 Environment 的 degradation_models 和各节点 NodeState 中，供执行时间退化估计使用。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：setup 通常只准备状态或外部资源，是否推进仿真时间取决于内部是否包含 yield。
        """
        super().setup(env)
        set_degradation(env, self.model_folder)


def get_model_file(folder, node_name):
    """
    根据节点名称选择对应的性能退化模型文件。

    节点名中的硬件类型片段会映射到 .sav 模型文件；无法识别时抛出 ValueError。

    参数说明：
    - folder: 模型文件或数据文件所在目录。
    - node_name: 节点名称。

    返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
    """
    if 'xeongpu' in node_name or 'xeoncpu' in node_name:
        file = 'eb-xeongpu.sav'
    elif 'nx' in node_name:
        file = 'eb-jetson-nx-01.sav'
    elif 'nano' in node_name:
        file = 'eb-jetson-nano-01.sav'
    elif 'tx2' in node_name:
        file = 'eb-jetson-tx2-01.sav'
    elif 'tpu' in node_name or 'coral' in node_name:
        file = 'eb-rpi4-01.sav'
    elif 'rpi3' in node_name:
        file = 'eb-rpi3-01.sav'
    elif 'rockpi' in node_name:
        file = 'eb-rockpi.sav'
    elif 'nuc' in node_name:
        file = 'eb-nuc7.sav'
    elif 'rpi4' in node_name:
        file = 'eb-rpi4-01.sav'
    else:
        raise ValueError(f"Can't find model for node: {node_name}")
    return os.path.join(folder, file)


def set_degradation(env: Environment, folder: str):
    """
    为环境中的节点加载性能退化模型。

    相同硬件类型的节点会复用同一个已加载模型，避免重复读取模型文件。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - folder: 模型文件或数据文件所在目录。 类型标注：str。

    返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
    """
    models = {}
    for ether_node in env.topology.get_nodes():
        try:
            name = ether_node.name[:ether_node.name.rindex("_")]
            model = models.get(name, None)
            if model is None:
                model_file = get_model_file(folder, name)
                model = loader.load_model(model_file)
                models[name] = model

            env.degradation_models[ether_node.name] = model
        except ValueError:
            pass
