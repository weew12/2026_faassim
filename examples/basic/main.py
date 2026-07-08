"""
faas-sim 基础仿真示例。

本示例展示一条最小但完整的仿真链路：
1. 创建 UrbanSensing 拓扑并初始化 Docker registry。
2. 在 benchmark setup 阶段注册函数镜像。
3. 构造两个函数部署：``python-pi`` 和 ``resnet50-inference``。
4. 部署函数并等待副本可用。
5. 并发触发 10 个 ``python-pi`` 请求和 10 个 ``resnet50-inference`` 请求。

后续示例中的自定义函数模拟器、请求生成器、调度器和结果分析，大多都以这个基础
工作流为起点。
"""

import logging
from typing import List

import ether.scenarios.urbansensing as scenario
from skippy.core.utils import parse_size_string

from sim import docker
from sim.benchmark import Benchmark
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import FunctionDeployment, FunctionRequest, Function, FunctionImage, ScalingConfiguration, \
    DeploymentRanking, FunctionContainer, KubernetesResourceConfiguration
from sim.faassim import Simulation
from sim.topology import Topology

logger = logging.getLogger(__name__)


def main():
    """
    创建拓扑和 benchmark，并启动仿真。
    """
    logging.basicConfig(level=logging.DEBUG)

    topology = example_topology()
    benchmark = ExampleBenchmark()

    sim = Simulation(topology, benchmark)
    sim.run()


def example_topology() -> Topology:
    """
    创建基础示例使用的网络拓扑。

    UrbanSensingScenario 会生成边缘设备、边缘服务器和云节点等实体；初始化 Docker
    registry 后，部署阶段才能按镜像名和架构查找可用镜像。
    """
    t = Topology()
    scenario.UrbanSensingScenario().materialize(t)
    t.init_docker_registry()

    return t


class ExampleBenchmark(Benchmark):
    """
    基础实验场景。

    Benchmark 负责定义仿真开始前的环境准备和仿真期间的工作负载。本类演示最常见
    的组织方式：注册镜像、创建 FunctionDeployment、部署函数、触发请求。
    """

    def setup(self, env: Environment):
        """
        注册本实验会用到的容器镜像。

        每个镜像注册 arm32、x86、aarch64 三种架构。调度和部署阶段会根据节点架构
        与 FunctionDeployment 中声明的镜像，选择可以拉取的镜像版本。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='arm32'))
        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='x86'))
        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='aarch64'))

        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='x86'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='aarch64'))

        containers.put(ImageProperties('resnet50-inference-gpu', parse_size_string('56M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-inference-gpu', parse_size_string('56M'), arch='x86'))
        containers.put(ImageProperties('resnet50-inference-gpu', parse_size_string('56M'), arch='aarch64'))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info('%s, %s, %s', name, tag, images)

    def run(self, env: Environment):
        """
        执行基础实验流程。

        run 是 SimPy 协程：部署、等待副本和函数调用都会通过 yield 交给仿真时钟
        推进。这里先部署两个函数，等副本可用后并发发起 20 个请求。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info('waiting for replica')
        yield env.process(env.faas.poll_available_replica('python-pi'))
        yield env.process(env.faas.poll_available_replica('resnet50-inference'))

        ps = []
        logger.info('executing 10 python-pi requests')
        for i in range(10):
            ps.append(env.process(env.faas.invoke(FunctionRequest('python-pi'))))

        logger.info('executing 10 resnet50-inference requests')
        for i in range(10):
            ps.append(env.process(env.faas.invoke(FunctionRequest('resnet50-inference'))))

        for p in ps:
            yield p

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        返回基础示例需要部署的两个函数。
        """
        resnet_fd = self.prepare_resnet_inference_deployment()

        python_pi_fd = self.prepare_python_pi_deployment()

        return [python_pi_fd, resnet_fd]

    def prepare_python_pi_deployment(self):
        """
        构造 ``python-pi`` 函数部署。

        ``python-pi`` 只提供 CPU 容器，使用默认伸缩配置，适合作为最简单的函数部署
        示例。
        """
        python_pi = 'python-pi'
        python_pi_cpu = FunctionImage(image='python-pi-cpu')
        python_pi_fn = Function(python_pi, fn_images=[python_pi_cpu])

        python_pi_fn_container = FunctionContainer(python_pi_cpu)

        python_pi_fd = FunctionDeployment(
            python_pi_fn,
            [python_pi_fn_container],
            ScalingConfiguration()
        )

        return python_pi_fd

    def prepare_resnet_inference_deployment(self):
        """
        构造 ``resnet50-inference`` 函数部署。

        该函数同时声明 GPU 和 CPU 两种镜像，并通过 DeploymentRanking 表示优先使用
        GPU 镜像、其次使用 CPU 镜像。GPU 容器额外声明 Kubernetes 风格资源请求。
        """
        resnet_inference = 'resnet50-inference'
        inference_cpu = 'resnet50-inference-cpu'
        inference_gpu = 'resnet50-inference-gpu'

        resnet_inference_gpu = FunctionImage(image=inference_gpu)
        resnet_inference_cpu = FunctionImage(image=inference_cpu)
        resnet_fn = Function(resnet_inference, fn_images=[resnet_inference_gpu, resnet_inference_cpu])

        resnet_cpu_container = FunctionContainer(resnet_inference_cpu)

        request = KubernetesResourceConfiguration.create_from_str(cpu='100m', memory='1024Mi')
        resnet_gpu_container = FunctionContainer(resnet_inference_gpu, resource_config=request)

        resnet_fd = FunctionDeployment(
            resnet_fn,
            [resnet_cpu_container, resnet_gpu_container],
            ScalingConfiguration(),
            DeploymentRanking([inference_gpu, inference_cpu])
        )

        return resnet_fd


if __name__ == '__main__':
    main()
