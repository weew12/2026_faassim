"""
文件作用：cache_aware_scheduler 样例使用的 Benchmark。

该 Benchmark 根据 workload 中出现的函数集合，逐个部署函数并触发请求。

重要说明：
faas-sim 的 DefaultFaasSystem.scale_up() 会按 container image 统计已部署副本数。
如果多个不同函数共用同一个 image，且每个 FunctionDeployment 的 scale_max=1，
第三个函数开始可能因为同一 image 的已部署计数超过 max_replicas 而不再创建副本，
最终表现为 poll_available_replica 一直等待。因此本样例为每个函数使用独立镜像名，
避免“多函数共享镜像”干扰缓存感知调度逻辑。
"""

import logging
from typing import Dict, List

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

from sim.faas import FunctionRequest as SimFunctionRequest

from workload import SchedulerRequest

logger = logging.getLogger(__name__)


class CacheAwareSchedulerBenchmark(Benchmark):
    """
    缓存感知调度 Benchmark。
    """

    image_suffix = "cache-aware-cpu"

    def __init__(self, scenario_name: str, workload: List[SchedulerRequest]):
        """
        初始化 Benchmark。
        """
        self.scenario_name = scenario_name
        self.workload = workload
        self.deployments: Dict[str, FunctionDeployment] = {}

    def setup(self, env: Environment):
        """
        注册函数镜像。

        每个函数使用独立镜像名，避免 faas-sim 内部按 image 统计副本数量时，
        把多个函数错误合并到同一个 scale_max 约束下。
        """
        containers: docker.ContainerRegistry = env.container_registry

        for function_name in self.function_names():
            image_name = self.image_name_for(function_name)

            containers.put(ImageProperties(image_name, parse_size_string("64M"), arch="arm32"))
            containers.put(ImageProperties(image_name, parse_size_string("64M"), arch="x86"))
            containers.put(ImageProperties(image_name, parse_size_string("64M"), arch="aarch64"))

            logger.info("registered image=%s for function=%s", image_name, function_name)

    def run(self, env: Environment):
        """
        运行缓存感知调度实验。
        """
        self.deployments = {
            function_name: self.prepare_deployment(function_name)
            for function_name in self.function_names()
        }

        for function_name, deployment in self.deployments.items():
            logger.info("deploying function=%s scenario=%s", function_name, self.scenario_name)
            yield from env.faas.deploy(deployment)
            yield from self.wait_for_available_replica(env, deployment)

        for request in self.workload:
            if env.now < request.arrival_time:
                yield env.timeout(request.arrival_time - env.now)

            deployment = self.deployments[request.function_name]

            env.metrics.log(
                "cache_aware_workload_request",
                {
                    "arrival_time": request.arrival_time,
                },
                scenario=self.scenario_name,
                function_name=request.function_name,
                request_id=request.request_id,
            )

            # 当前 faas-sim 版本中的 FunctionRequest 构造函数只接受 name 和 size，
            # request_id 由内部计数器生成，不支持 request_id=... 关键字参数。
            # 为了让输出结果继续使用 workload.csv 中的请求编号，这里先按原生方式构造，
            # 再覆盖 request_id 字段。
            sim_request = SimFunctionRequest(request.function_name)
            sim_request.request_id = request.request_id

            # 当前 faas-sim 版本中 DefaultFaasSystem.invoke() 只接收 FunctionRequest，
            # 函数名从 sim_request.name 中读取，不需要额外传入 deployment。
            yield env.process(env.faas.invoke(sim_request))

        yield env.timeout(1)

    def wait_for_available_replica(self, env: Environment, deployment: FunctionDeployment, timeout: float = 30.0):
        """
        等待函数副本可用，并设置仿真时间超时。

        如果副本没有进入 RUNNING 状态，说明部署或调度过程存在问题；
        超时可以避免样例无提示地长时间等待。
        """
        poll_process = env.process(env.faas.poll_available_replica(deployment.name))
        timeout_event = env.timeout(timeout)

        result = yield poll_process | timeout_event

        if poll_process not in result:
            raise RuntimeError(
                f"等待函数副本可用超时：function={deployment.name}, timeout={timeout}. "
                f"请检查该函数是否创建了副本、调度器是否被调用、镜像是否已注册。"
            )

    def prepare_deployment(self, function_name: str) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        image_name = self.image_name_for(function_name)
        fn_image = FunctionImage(image=image_name)
        fn = Function(function_name, fn_images=[fn_image])

        # 本样例会一次性部署 workload 中出现的多个函数。
        # 为避免小型 UrbanSensing 节点因资源不足导致副本 Pending，
        # 这里使用较小资源请求，重点观察缓存状态对调度结果的影响。
        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="20m",
            memory="32Mi",
        )

        container = FunctionContainer(
            fn_image,
            resource_config=resource_config,
            labels={
                "cache.edgerun.io/function": function_name,
            },
        )

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 1
        scaling_config.scale_max = 1

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )

    def function_names(self) -> List[str]:
        """
        返回 workload 中出现的函数集合。
        """
        return sorted({request.function_name for request in self.workload})

    def image_name_for(self, function_name: str) -> str:
        """
        返回函数对应的独立镜像名。
        """
        safe_name = function_name.replace("_", "-")
        return f"{safe_name}-{self.image_suffix}"
