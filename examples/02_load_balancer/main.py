"""
文件作用：faas-sim 原生负载均衡样例。

本样例演示如何观察 faas-sim 中的负载均衡行为，包括：
- 部署一个拥有多个副本的函数；
- 替换 DefaultFaasSystem 中的负载均衡器；
- 使用轮询策略将请求分发到不同副本；
- 记录 load_balancer 指标；
- 导出路由分布与调用结果。

运行方式：
    python -u examples/02_load_balancer/main.py
"""

import logging
import sys
from pathlib import Path
from typing import List

from ether.core import Node, Link, Connection, Capacity
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
    FunctionState,
)
from sim.faassim import Simulation
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from simulator import LoadBalancerSimulatorFactory
from system import create_load_balancer_faas_system

logger = logging.getLogger(__name__)


def configure_logging():
    """
    配置日志输出。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


# 全局复用：避免 ether.scenarios.urbansensing 的内部状态污染
# （13_image_cache / 14 / 19 已经踩过这个坑 —— 连续两次 UrbanSensingScenario() 产生不同节点集）
# 02 只跑一次 sim，目前未踩坑，但为了与其他样例保持一致，统一改用最小 4-server 拓扑。
_SHARED_TOPOLOGY: Topology = None


def example_topology() -> Topology:
    """
    创建负载均衡样例使用的最小 4-server 拓扑。

    为什么不复用 UrbanSensingScenario：
    ether.scenarios.urbansensing 在连续构造时会返回不同的节点集
    （server_0..9、server_10..19、...、server_70..79），可能导致后续扩展
    时把同一份 topology 跑两次出现节点不匹配。这里用 ether.core 直接
    构造 4 个 server 节点 + Docker Registry，构造一次复用。

    返回：每次调用都返回同一份 Topology 对象。
    """
    global _SHARED_TOPOLOGY
    if _SHARED_TOPOLOGY is None:
        topology = Topology()

        cap = Capacity(cpu_millis=4000, memory=2 * 1024 * 1024 * 1024)

        # 镜像拉取链路：DockerRegistry -- internet_link -- switch -- link_server_X -- server_X
        registry_link = Link(bandwidth=200, tags={"name": "registry_link", "type": "registry_access"})
        topology.add_connection(Connection("internet", registry_link, latency=5))
        topology.add_connection(Connection(registry_link, "switch", latency=5))

        for i in range(4):
            node = Node(f"server_{i}", capacity=cap, arch="x86")
            link = Link(bandwidth=200, tags={"name": f"link_server_{i}", "type": "node_access"})
            topology.add_connection(Connection(node, link, latency=2))
            topology.add_connection(Connection(link, "switch", latency=1))

        topology.init_docker_registry()
        _SHARED_TOPOLOGY = topology

    return _SHARED_TOPOLOGY


class LoadBalancerBenchmark(Benchmark):
    """
    负载均衡实验 Benchmark。

    该 Benchmark 部署一个函数 load-balanced-python-pi，
    将最小副本数设置为 3，然后触发 30 个请求。
    在多个 RUNNING 副本存在时，FaaS 系统会调用负载均衡器选择目标副本。
    """

    function_name = "load-balanced-python-pi"
    image_name = "load-balanced-python-pi-cpu"
    expected_replicas = 3

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("58M"), arch="arm32"))
        containers.put(ImageProperties(self.image_name, parse_size_string("58M"), arch="x86"))
        containers.put(ImageProperties(self.image_name, parse_size_string("58M"), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行负载均衡实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for %d running replicas", self.expected_replicas)
        yield env.process(self.wait_running_replicas(env, self.function_name, self.expected_replicas))

        logger.info("triggering load balancer workload")
        ia_generator = static_arrival_profile(constant_rps_profile(rps=20))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=30,
        )

        # 等所有 invoke 进程完成。
        # function_trigger(max_requests=N) 只保证触发 N 个请求就返回，
        # 不等待 N 次 invoke 全部跑完。在本样例中每个 invoke 耗时 0.3s，
        # 留 2s 缓冲即可让 30 个请求全部完成并写入 invocations.csv，
        # 使 route_events == invocation_events，summary 数据自洽。
        yield env.timeout(2.0)

        logger.info("load balancer workload finished")

    def wait_running_replicas(self, env: Environment, fn_name: str, expected: int, interval: float = 0.5):
        """
        等待指定函数达到预期 RUNNING 副本数量。

        参数：
        - env：faas-sim 运行时环境；
        - fn_name：函数名称；
        - expected：预期 RUNNING 副本数；
        - interval：轮询间隔。
        """
        while True:
            running = env.faas.get_replicas(fn_name, FunctionState.RUNNING)
            if len(running) >= expected:
                logger.info("%s has %d running replicas", fn_name, len(running))
                return

            logger.info(
                "[simtime=%.2f] waiting running replicas for %s: current=%d expected=%d",
                env.now,
                fn_name,
                len(running),
                expected,
            )
            yield env.timeout(interval)

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_load_balanced_python_pi_deployment()]

    def prepare_load_balanced_python_pi_deployment(self) -> FunctionDeployment:
        """
        准备负载均衡函数部署对象。

        scale_min=3 表示部署后至少保持 3 个运行副本；
        scale_max=3 表示本样例不引入自动伸缩，只观察负载均衡行为。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="100m",
            memory="128Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 3
        scaling_config.scale_max = 3

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    负载均衡样例入口。
    """
    configure_logging()

    logger.info("creating load balancer topology")
    topology = example_topology()

    logger.info("creating load balancer benchmark")
    benchmark = LoadBalancerBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 替换 FaaS 系统，使其使用可观测轮询负载均衡器。
    sim.create_faas_system = create_load_balancer_faas_system

    # 使用稳定执行时间模拟器，便于观察请求路由分布。
    sim.create_simulator_factory = LoadBalancerSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    summary_df = dfs.get("load_balancer_summary")
    if summary_df is not None:
        logger.info("load balancer summary:\n%s", summary_df.to_string(index=False))

    distribution_df = dfs.get("load_balancer_replica_distribution")
    if distribution_df is not None and len(distribution_df) > 0:
        logger.info("load balancer distribution:\n%s", distribution_df.to_string(index=False))

    paper_df = dfs.get("load_balancer_paper_highlight")
    if paper_df is not None and len(paper_df) > 0:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    self_check_df = dfs.get("load_balancer_self_check")
    if self_check_df is not None and len(self_check_df) > 0:
        passed = int(self_check_df["passed"].sum())
        total = len(self_check_df)
        logger.info("data self-check: %d / %d PASS", passed, total)
        if passed < total:
            for _, row in self_check_df[~self_check_df["passed"]].iterrows():
                logger.warning("  FAILED: %s", row["check_id"])

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
