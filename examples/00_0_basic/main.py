"""
文件作用：基础示例，展示如何创建拓扑、注册镜像、定义函数部署、部署函数并发起简单请求负载。
主要类：ExampleBenchmark。
主要函数：main、example_topology。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
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
    logging.basicConfig(level=logging.DEBUG)

    topology = example_topology()
    benchmark = ExampleBenchmark()
    
    sim = Simulation(topology, benchmark)
    sim.run()


def example_topology() -> Topology:
    """
    函数作用：处理 example、topology 相关业务逻辑。
    """
    t = Topology()
    scenario.UrbanSensingScenario().materialize(t)
    t.init_docker_registry()

    return t


class ExampleBenchmark(Benchmark):

    """
    类作用：ExampleBenchmark 实验场景类，组织镜像、函数部署和请求负载。
    """
    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
        - 触发函数调用并等待响应，用于工作负载生成或复合调用流程。
        - 调用部署接口上线函数或副本。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield from env.faas.deploy(deployment)

        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        logger.info('waiting for replica')
        # 协程同步：等待子过程完成，保证业务阶段按顺序衔接。
        yield env.process(env.faas.poll_available_replica('python-pi'))
        # 协程同步：等待子过程完成，保证业务阶段按顺序衔接。
        yield env.process(env.faas.poll_available_replica('resnet50-inference'))

        
        ps = []
        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        logger.info('executing 10 python-pi requests')
        for i in range(10):
            # 请求触发：把生成的请求交给 FaaS 系统执行。
            ps.append(env.process(env.faas.invoke(FunctionRequest('python-pi'))))

        logger.info('executing 10 resnet50-inference requests')
        for i in range(10):
            # 请求触发：把生成的请求交给 FaaS 系统执行。
            ps.append(env.process(env.faas.invoke(FunctionRequest('resnet50-inference'))))

        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        for p in ps:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield p

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        函数作用：准备实验所需的函数、镜像或部署配置。
        """
        resnet_fd = self.prepare_resnet_inference_deployment()

        python_pi_fd = self.prepare_python_pi_deployment()

        return [python_pi_fd, resnet_fd]

    def prepare_python_pi_deployment(self):
        
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
