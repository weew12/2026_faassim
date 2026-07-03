"""
文件作用：watchdog 示例入口，组合训练和推理函数模拟器，展示 OpenFaaS HTTP/Fork 风格执行模型。
主要类：AIFunctionSimulatorFactory、TrainInferenceBenchmark。
主要函数：main。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
"""

import logging
from typing import List

from ether.util import parse_size_string

import examples.basic.main as basic
from examples.watchdogs.inference import InferenceFunctionSim
from examples.watchdogs.training import TrainingFunctionSim
from sim import docker
from sim.benchmark import Benchmark
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import SimulatorFactory, FunctionContainer, FunctionSimulator, FunctionDeployment, ScalingConfiguration, \
    DeploymentRanking, FunctionImage, Function, FunctionRequest
from sim.faassim import Simulation

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


class AIFunctionSimulatorFactory(SimulatorFactory):

    """
    类作用：AIFunctionSimulatorFactory 工厂类，负责根据函数或配置创建对应组件实例。
    继承关系：SimulatorFactory。
    核心方法：create。
    """
    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if 'inference' in fn.fn_image.image:
            return InferenceFunctionSim(4)
        elif 'training' in fn.fn_image.image:
            return TrainingFunctionSim()


def main():
    """
    函数作用：处理 main 相关业务逻辑。
    关键流程：
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    logging.basicConfig(level=logging.INFO)

    # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
    sim = Simulation(basic.example_topology(), TrainInferenceBenchmark())

    
    sim.create_simulator_factory = AIFunctionSimulatorFactory

    
    sim.run()
    dfs = {
        'fets_df': sim.env.metrics.extract_dataframe('fets')
    }
    pass


class TrainInferenceBenchmark(Benchmark):

    """
    类作用：TrainInferenceBenchmark 实验场景类，组织镜像、函数部署和请求负载。
    继承关系：Benchmark。
    核心方法：setup、run、prepare_deployments、prepare_resnet_training_deployment、prepare_resnet_inference_deployment。
    """
    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='x86'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='aarch64'))

        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='x86'))
        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='aarch64'))

        # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
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
        yield env.process(env.faas.poll_available_replica('resnet50-training'))
        # 协程同步：等待子过程完成，保证业务阶段按顺序衔接。
        yield env.process(env.faas.poll_available_replica('resnet50-inference'))

        
        ps = []
        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        logger.info('executing 10 resnet50-training requests')
        for i in range(10):
            # 请求触发：把生成的请求交给 FaaS 系统执行。
            ps.append(env.process(env.faas.invoke(FunctionRequest('resnet50-training'))))

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
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        resnet_inference_fd = self.prepare_resnet_inference_deployment()

        resnet_training_fd = self.prepare_resnet_training_deployment()

        return [resnet_training_fd, resnet_inference_fd]

    def prepare_resnet_training_deployment(self):
        

        """
        函数作用：准备实验所需的函数、镜像或部署配置。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        resnet_training = 'resnet50-training'
        training_cpu = 'resnet50-training-cpu'

        resnet_training_cpu = FunctionImage(image=training_cpu)
        resnet_fn = Function(resnet_training, fn_images=[resnet_training_cpu])

        

        resnet_cpu_container = FunctionContainer(resnet_training_cpu)

        resnet_fd = FunctionDeployment(
            resnet_fn,
            [resnet_cpu_container],
            ScalingConfiguration(),
            DeploymentRanking([training_cpu])
        )

        return resnet_fd

    def prepare_resnet_inference_deployment(self):
        

        """
        函数作用：准备实验所需的函数、镜像或部署配置。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        resnet_inference = 'resnet50-inference'
        inference_cpu = 'resnet50-inference-cpu'

        resnet_inference_cpu = FunctionImage(image=inference_cpu)
        resnet_fn = Function(resnet_inference, fn_images=[resnet_inference_cpu])

        

        resnet_cpu_container = FunctionContainer(resnet_inference_cpu)

        resnet_fd = FunctionDeployment(
            resnet_fn,
            [resnet_cpu_container],
            ScalingConfiguration(),
            DeploymentRanking([inference_cpu])
        )

        return resnet_fd


if __name__ == '__main__':
    main()
