"""
文件作用：batch_experiment 样例使用的 Benchmark。

该 Benchmark 根据 ExperimentCase 的负载配置部署函数并触发请求。
"""

import logging
from typing import List

from skippy.core.utils import parse_size_string

from sim import docker
from sim.benchmark import Benchmark
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import (
    FunctionDeployment,
    Function,
    FunctionImage,
    ScalingConfiguration,
    FunctionContainer,
    KubernetesResourceConfiguration,
)
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile

from experiment_config import ExperimentCase

logger = logging.getLogger(__name__)


class BatchExperimentBenchmark(Benchmark):
    """
    批量实验 Benchmark。
    """

    function_name = "batch-exp-python-pi"
    image_name = "batch-exp-python-pi-cpu"

    def __init__(self, case: ExperimentCase):
        """
        初始化 Benchmark。
        """
        self.case = case

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("48M"), arch="arm32"))
        containers.put(ImageProperties(self.image_name, parse_size_string("48M"), arch="x86"))
        containers.put(ImageProperties(self.image_name, parse_size_string("48M"), arch="aarch64"))

    def run(self, env: Environment):
        """
        运行单次实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        ia_generator = static_arrival_profile(
            constant_rps_profile(rps=self.case.workload.rps)
        )

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=self.case.workload.max_requests,
        )

        # 等待尾部请求完成，保证指标完整。
        yield env.timeout(2)

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_function_deployment()]

    def prepare_function_deployment(self) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="150m",
            memory="128Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 2
        scaling_config.scale_max = 2

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )
