"""
请求生成器示例。

本示例展示如何使用 ``sim.requestgen`` 为函数调用生成请求流：
- ``constant_rps_profile(rps=20)`` 给出固定平均请求速率。
- ``expovariate_arrival_profile(...)`` 把 RPS 转换成指数分布到达间隔。
- ``function_trigger(...)`` 按这些到达间隔持续触发 FaaS 调用。

示例部署一个 ``python-pi`` 函数，并生成最多 100 个请求。
"""

import logging
from typing import List

import ether.scenarios.urbansensing as scenario
from skippy.core.utils import parse_size_string

from sim import docker
from sim.benchmark import Benchmark
from sim.core import Environment
from sim.docker import ImageProperties
from sim.faas import FunctionDeployment, Function, FunctionImage, ScalingConfiguration, \
    FunctionContainer
from sim.faassim import Simulation
from sim.requestgen import function_trigger, constant_rps_profile, expovariate_arrival_profile
from sim.topology import Topology

logger = logging.getLogger(__name__)


def main():
    """
    构建拓扑和 benchmark，然后启动仿真。

    请求生成逻辑在 ``ExampleBenchmark.run`` 中执行；这里负责把拓扑、benchmark
    和 Simulation 组装起来。
    """
    logging.basicConfig(level=logging.DEBUG)

    topology = example_topology()
    benchmark = ExampleBenchmark()

    sim = Simulation(topology, benchmark)
    sim.run()


def example_topology() -> Topology:
    """
    创建 UrbanSensing 拓扑并初始化 Docker registry。

    UrbanSensingScenario 会生成一组边缘/云节点；Docker registry 初始化后，后续
    benchmark setup 阶段注册的镜像才能被部署过程查询和拉取。
    """
    t = Topology()
    scenario.UrbanSensingScenario().materialize(t)
    t.init_docker_registry()

    return t


class ExampleBenchmark(Benchmark):
    """
    单函数请求生成 benchmark。

    该 benchmark 只部署一个 ``python-pi`` 函数，用固定平均 RPS 的随机到达流
    触发请求，便于观察 request generator 如何驱动 FaaS invoke。
    """

    def setup(self, env: Environment):
        """
        注册 python-pi 函数镜像。

        同一个镜像注册 arm32、x86 和 aarch64 三种架构，保证不同架构节点都有可选
        镜像版本。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='arm32'))
        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='x86'))
        containers.put(ImageProperties('python-pi-cpu', parse_size_string('58M'), arch='aarch64'))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info('%s, %s, %s', name, tag, images)

    def run(self, env: Environment):
        """
        部署函数并按随机到达间隔触发请求。

        请求流含义：
        - 平均速率为 20 RPS。
        - 相邻请求间隔服从指数分布，模拟 Poisson arrival。
        - 最多触发 100 个 ``python-pi`` 请求。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info('waiting for replica')
        yield env.process(env.faas.poll_available_replica('python-pi'))

        # 固定平均 RPS，再转换成指数分布到达间隔。
        ia_generator = expovariate_arrival_profile(constant_rps_profile(rps=20))

        # function_trigger 根据到达间隔反复调用 env.faas.invoke。
        yield from function_trigger(env, deployments[0], ia_generator, max_requests=100)

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        返回本 benchmark 需要部署的函数列表。
        """
        python_pi_fd = self.prepare_python_pi_deployment()

        return [python_pi_fd]

    def prepare_python_pi_deployment(self):
        """
        构造 python-pi 的 FunctionDeployment。

        ``Function`` 描述函数名和可用镜像，``FunctionContainer`` 描述可部署容器，
        ``ScalingConfiguration`` 使用默认伸缩配置。
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


if __name__ == '__main__':
    main()
