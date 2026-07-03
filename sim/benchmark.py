"""
文件作用：通用 Benchmark 基类，描述实验如何注册镜像、部署函数、启动请求生成器，并在仿真时间内维持工作负载。
主要类：Benchmark、BenchmarkBase、DegradationBenchmarkBase。
主要函数：get_model_file、set_degradation。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
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
    
    # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。

    """
    类作用：Benchmark 抽象基类，规定实验 setup 和 run 两个阶段。
    核心方法：setup、run。
    """
    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        pass

    def run(self, env: Environment):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(0)


class BenchmarkBase(Benchmark):
    """
    类作用：通用 Benchmark 实现，统一处理镜像注册、函数部署、请求生成器启动和实验等待。
    继承关系：Benchmark。
    核心方法：__init__、__create_deployments_per_name、setup、register_images、run、wait。
    """
    def __init__(self, images: List[Tuple[str, str, str]], deployments: List[FunctionDeployment],
                 arrival_profiles: Dict[str, Generator], duration: int = None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：arrival_profiles、deployments、deployments_per_name、duration、images。
        参数：images：容器镜像集合。；deployments：函数部署集合。；arrival_profiles：请求到达模型集合。；duration：实验持续时间。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.duration：Benchmark 持续的仿真时间长度。
        self.duration = duration  
        # 字段说明：self.images：容器镜像元数据集合，供容器仓库注册和部署阶段查找。
        self.images = images
        # 字段说明：self.deployments：函数部署集合，描述本次实验要上线的函数及其配置。
        self.deployments = deployments
        # 字段说明：self.deployments_per_name：按函数名分组的部署索引，方便 Benchmark 根据请求目标快速查找部署。
        self.deployments_per_name = self.__create_deployments_per_name()
        # 字段说明：self.arrival_profiles：请求到达模型集合，决定每个函数的请求强度和时间分布。
        self.arrival_profiles = arrival_profiles

    def __create_deployments_per_name(self):
        """
        函数作用：处理 create、deployments、per、name 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        deployments_per_name = {}
        for deployment in self.deployments:
            deployments_per_name[deployment.name] = deployment
        return deployments_per_name

    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().setup(env)
        self.register_images(env)

    def register_images(self, env: Environment):
        """
        函数作用：把实验需要使用的容器镜像登记到仿真的容器仓库。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        containers: docker.ContainerRegistry = env.container_registry
        for image, size, arch in self.images:
            containers.put(ImageProperties(image, parse_size_string(size), arch=arch))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logging.info('%s, %s, %s', name, tag, images)

    def run(self, env: Environment):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
        - 调用部署接口上线函数或副本。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        for deployment in self.deployments:
            # 仿真推进：向 SimPy 事件队列交出控制权。
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

        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from ps

    def wait(self, env, ps):
        """
        函数作用：等待一组 SimPy 进程完成，用于同步请求生成器或部署过程。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；ps：表示 ps，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(env.now + self.duration)
        for p in ps:
            p.interrupt('stop')


class DegradationBenchmarkBase(BenchmarkBase):

    """
    类作用：带性能退化模型的 Benchmark，在 setup 阶段加载节点级退化模型。
    继承关系：BenchmarkBase。
    核心方法：__init__、setup。
    """
    def __init__(self, images: List[Tuple[str, str, str]], deployments: List[FunctionDeployment],
                 arrival_profiles: Dict[str, Generator], duration: int = None, model_folder='./data'):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：model_folder。
        参数：images：容器镜像集合。；deployments：函数部署集合。；arrival_profiles：请求到达模型集合。；duration：实验持续时间。；model_folder：性能退化模型所在目录。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__(images, deployments, arrival_profiles, duration)
        # 字段说明：self.model_folder：性能退化模型文件所在目录。
        self.model_folder = model_folder

    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().setup(env)
        set_degradation(env, self.model_folder)


def get_model_file(folder, node_name):
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：folder：输入或输出目录。；node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：更新对象内部状态或实验配置。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；folder：输入或输出目录。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
            # 业务说明：这里处理节点、拓扑或网络连接相关状态。
            pass
