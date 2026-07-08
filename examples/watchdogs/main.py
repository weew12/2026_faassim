"""
Watchdog 示例入口。

本示例把同一个实验场景拆成两类函数：
- resnet50-training：使用 ForkingWatchdog，表示每次请求都独立启动/执行一次任务。
- resnet50-inference：使用 HTTPWatchdog，表示副本内部有固定数量的 HTTP worker 并发处理请求。

运行该文件可以观察两种 OpenFaaS watchdog 执行模型在 faas-sim 中如何接入部署、
副本启动、函数调用和 FET(Function Execution Time) 指标记录流程。
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

logger = logging.getLogger(__name__)


class AIFunctionSimulatorFactory(SimulatorFactory):
    """
    根据函数镜像名选择具体的 FunctionSimulator。

    faas-sim 在部署 FunctionContainer 时会调用该工厂。这里用镜像名中的
    ``inference`` / ``training`` 关键字，把两个函数分别绑定到 HTTP watchdog
    和 forking watchdog 示例实现。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        为当前函数容器创建模拟器实例。

        ``env`` 由平台传入；本示例不直接读取它，但保留参数以匹配
        ``SimulatorFactory`` 接口。
        """
        if 'inference' in fn.fn_image.image:
            return InferenceFunctionSim(4)
        elif 'training' in fn.fn_image.image:
            return TrainingFunctionSim()


def main():
    """
    构造拓扑、实验负载和 watchdog 工厂，然后启动仿真。

    仿真结束后从 metrics 中取出 ``fets`` 表，便于调试时查看每次函数执行的
    开始/结束时间、所在节点和请求编号。
    """
    logging.basicConfig(level=logging.INFO)

    sim = Simulation(basic.example_topology(), TrainInferenceBenchmark())

    # 用本示例的工厂覆盖默认函数模拟器创建逻辑。
    sim.create_simulator_factory = AIFunctionSimulatorFactory

    sim.run()
    dfs = {
        'fets_df': sim.env.metrics.extract_dataframe('fets')
    }
    pass


class TrainInferenceBenchmark(Benchmark):
    """
    训练/推理混合负载 benchmark。

    setup 阶段注册可用镜像，run 阶段部署两个函数并发起 20 个请求：
    10 个 training 请求和 10 个 inference 请求。这个场景用于突出两种
    watchdog 模式的并发语义差异。
    """

    def setup(self, env: Environment):
        """
        向容器镜像仓库注册训练和推理镜像。

        每个镜像注册 arm32、x86、aarch64 三种架构，调度器可以根据节点架构
        选择可拉取的镜像版本。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='x86'))
        containers.put(ImageProperties('resnet50-inference-cpu', parse_size_string('56M'), arch='aarch64'))

        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='arm32'))
        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='x86'))
        containers.put(ImageProperties('resnet50-training-cpu', parse_size_string('128M'), arch='aarch64'))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info('%s, %s, %s', name, tag, images)

    def run(self, env: Environment):
        """
        部署函数，等待副本可用，然后并发触发训练和推理请求。

        ``yield from env.faas.deploy`` 会把部署过程交给 SimPy 事件队列推进；
        ``env.process(env.faas.invoke(...))`` 用于并发提交请求，最后逐个等待完成。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info('waiting for replica')
        yield env.process(env.faas.poll_available_replica('resnet50-training'))
        yield env.process(env.faas.poll_available_replica('resnet50-inference'))

        ps = []
        logger.info('executing 10 resnet50-training requests')
        for i in range(10):
            ps.append(env.process(env.faas.invoke(FunctionRequest('resnet50-training'))))

        logger.info('executing 10 resnet50-inference requests')
        for i in range(10):
            ps.append(env.process(env.faas.invoke(FunctionRequest('resnet50-inference'))))

        for p in ps:
            yield p

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        创建 benchmark 需要部署的两个 FunctionDeployment。
        """
        resnet_inference_fd = self.prepare_resnet_inference_deployment()

        resnet_training_fd = self.prepare_resnet_training_deployment()

        return [resnet_training_fd, resnet_inference_fd]

    def prepare_resnet_training_deployment(self):
        """
        构造训练函数部署。

        训练函数只提供一个 CPU 镜像；具体使用 ForkingWatchdog 还是其他模拟器，
        由 ``AIFunctionSimulatorFactory`` 在部署容器时决定。
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
        构造推理函数部署。

        推理函数使用 CPU 镜像，并在模拟器工厂中被绑定到 4-worker 的
        ``InferenceFunctionSim``。
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
