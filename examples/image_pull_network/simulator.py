"""
文件作用：image_pull_network 样例使用的函数生命周期模拟器。

该模拟器重点观测 deploy 阶段中的 docker.pull()：
- deploy 开始时记录当前仿真时间；
- 调用 docker.pull() 模拟镜像拉取；
- deploy 结束后记录拉取耗时；
- 如果同一节点已有镜像，docker.pull() 会快速返回，耗时接近 0。
"""

import logging

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
)

logger = logging.getLogger(__name__)


class ImagePullSimulatorFactory(SimulatorFactory):
    """
    image_pull_network 样例的函数模拟器工厂。
    """

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return ImagePullFunctionSimulator()


class ImagePullFunctionSimulator(FunctionSimulator):
    """
    镜像拉取观测模拟器。

    该模拟器重点记录 deploy 阶段镜像拉取耗时。
    startup/setup/invoke 设置为较小固定值，避免干扰镜像拉取分析。
    """

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，并记录镜像拉取耗时。

        说明：
        - 第一次在某节点部署镜像时，docker.pull() 会触发网络 Flow；
        - 如果该节点已经缓存同一个 ImageProperties，docker.pull() 会直接返回；
        - 因此 image_pull_duration 可以近似反映镜像是否被重复拉取。
        """
        started = env.now
        image = replica.container.image
        node_name = replica.node.name

        logger.info(
            "[simtime=%.4f] begin docker.pull function=%s image=%s node=%s",
            env.now,
            replica.function.name,
            image,
            node_name,
        )

        yield from docker.pull(env, image, replica.node.ether_node)

        duration = env.now - started

        logger.info(
            "[simtime=%.4f] finish docker.pull function=%s image=%s node=%s duration=%.6f",
            env.now,
            replica.function.name,
            image,
            node_name,
            duration,
        )

        env.metrics.log(
            "image_pull_probe",
            {
                "image_pull_duration": duration,
                "cache_hit_like": duration <= 1e-9,
            },
            function_name=replica.function.name,
            image=image,
            node_name=node_name,
            replica_id=id(replica),
        )

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        yield env.timeout(0.1)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        本样例重点是镜像拉取，调用阶段只保留极小固定耗时。
        """
        yield env.timeout(0.05)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
