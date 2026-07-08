"""
文件作用：image_cache 样例使用的函数生命周期模拟器。

该模拟器重点观测 deploy 阶段：
- docker.pull() 前检查节点是否已有镜像；
- 调用 docker.pull()；
- docker.pull() 后记录耗时与缓存状态；
- 将镜像缓存探针写入 image_cache_probe 指标。
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


class ImageCacheSimulatorFactory(SimulatorFactory):
    """
    image_cache 样例的函数模拟器工厂。
    """

    def __init__(self, scenario_name: str):
        """
        初始化模拟器工厂。
        """
        self.scenario_name = scenario_name

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return ImageCacheFunctionSimulator(self.scenario_name)


class ImageCacheFunctionSimulator(FunctionSimulator):
    """
    镜像缓存观测模拟器。

    样例重点：
    - 首次部署同一镜像时，节点本地镜像缓存为空，docker.pull() 产生网络流；
    - 同一节点再次部署相同镜像时，docker.pull() 直接返回；
    - 不同节点首次部署相同镜像时，每个节点都需要各自拉取。
    """

    def __init__(self, scenario_name: str):
        """
        初始化模拟器。
        """
        self.scenario_name = scenario_name

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，并记录镜像缓存状态。
        """
        image_str = replica.container.image
        node = replica.node
        node_state = env.get_node_state(node.name)

        images = env.container_registry.find(image_str, arch=node.arch)
        if not images:
            raise ValueError(f"image not in registry: {image_str} arch={node.arch}")

        image = images[0]
        cache_hit_before = bool(node_state and image in node_state.docker_images)
        cached_image_count_before = len(node_state.docker_images) if node_state is not None else 0

        started = env.now

        logger.info(
            "[simtime=%.4f] image cache deploy begin scenario=%s function=%s image=%s node=%s cache_hit_before=%s",
            env.now,
            self.scenario_name,
            replica.function.name,
            image_str,
            node.name,
            cache_hit_before,
        )

        yield from docker.pull(env, image_str, node.ether_node)

        duration = env.now - started

        cache_hit_after = bool(node_state and image in node_state.docker_images)
        cached_image_count_after = len(node_state.docker_images) if node_state is not None else 0

        logger.info(
            "[simtime=%.4f] image cache deploy finish scenario=%s function=%s image=%s node=%s duration=%.6f cache_hit_after=%s",
            env.now,
            self.scenario_name,
            replica.function.name,
            image_str,
            node.name,
            duration,
            cache_hit_after,
        )

        env.metrics.log(
            "image_cache_probe",
            {
                "image_size": image.size,
                "cache_hit_before": cache_hit_before,
                "cache_hit_after": cache_hit_after,
                "pull_duration": duration,
                "cached_image_count_before": cached_image_count_before,
                "cached_image_count_after": cached_image_count_after,
            },
            scenario=self.scenario_name,
            function_name=replica.function.name,
            image=image_str,
            node_name=node.name,
            replica_id=id(replica),
            image_arch=image.arch,
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

        本样例重点是镜像缓存，调用阶段只保留极小固定耗时。
        注意：13 默认不触发 invoke（main.py benchmark.run() 只部署不调用），
        所以 invoke_dispatch_probe 实际为 0 行；保留这个探针是为了和 02-12 模式对齐，
        方便其他场景复用 simulator。

        关键探针（沿用 02-12 的 invoke_dispatch_probe 模式）：
        入口 simtime + replica_id + request_id + expected_t_exec（按 0.05s 真实派发），
        用于 probe×invocation join 自洽检查（如果 main.py 触发 invoke）。
        """
        # 派发探针（沿用 02-12 模式）
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
                "request_id": request.request_id,
                "expected_t_exec": 0.05,
            },
            function_name=replica.function.name,
            node=replica.node.name,
        )

        yield env.timeout(0.05)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
