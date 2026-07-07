"""
文件作用：faas-sim 冷启动生命周期拆分样例。

本样例演示如何将函数副本从创建到可用的过程拆分为 deploy、startup、setup，
并进一步区分 first_invoke 与 warm_invoke。该样例重点用于理解冷启动路径，
为后续冷启动感知缓存和预热策略提供基础。

运行方式：
    python -u examples/12_cold_start/main.py
"""

import logging
import sys
from pathlib import Path
from typing import List

import ether.scenarios.urbansensing as scenario
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
from sim.faassim import Simulation
from sim.requestgen import function_trigger, constant_rps_profile, static_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from simulator import ColdStartSimulatorFactory

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


def example_topology() -> Topology:
    """
    创建 cold_start 样例使用的拓扑。

    当前复用 UrbanSensingScenario，并初始化 Docker Registry。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


def wait_for_invocations(env, expected_count: int, max_wait: float = 30.0, poll_interval: float = 0.1):
    """
    轮询 env.metrics.records 直到 invocations 记录数达到 expected_count，
    或等到 max_wait simtime 秒后退出（避免死等）。

    faas-sim 的 function_trigger(max_requests=N) 只保证 N 个请求被触发（queued），
    不等待 N 次 invoke 全部跑完。原来的实现用 `env.timeout(2)` 硬等待，
    当 first_invoke_duration 变大或后续接入 scale-from-zero 时容易丢请求；
    这里改成"看到 N 条 invocations 记录"。

    返回：实际等待的 simtime 秒数。
    """
    start = env.now
    while env.now - start < max_wait:
        count = sum(
            1 for r in env.metrics.records if r.measurement == "invocations"
        )
        if count >= expected_count:
            return env.now - start
        yield env.timeout(poll_interval)
    return env.now - start


class ColdStartBenchmark(Benchmark):
    """
    冷启动实验 Benchmark。

    该 Benchmark 部署一个函数并触发三次请求：
    - 第一次请求用于观测 first_invoke；
    - 后两次请求用于观测 warm_invoke；
    - deploy / startup / setup 在副本启动阶段自动记录。
    """

    function_name = "cold-start-python-pi"
    image_name = "cold-start-python-pi-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("96M"), arch="arm32"))
        containers.put(ImageProperties(self.image_name, parse_size_string("96M"), arch="x86"))
        containers.put(ImageProperties(self.image_name, parse_size_string("96M"), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行冷启动实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        logger.info("triggering cold start workload")

        # 控制请求间隔，保证能清晰观察 first_invoke 与 warm_invoke。
        ia_generator = static_arrival_profile(constant_rps_profile(rps=2))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=3,
        )

        # 等待尾部请求完成，保证调用指标完整写入。
        # 原来用 env.timeout(2) 硬等待，这里轮询 env.metrics.records
        # 直到 invocations 数达到 3，或最多等 10 simtime 秒。
        expected_total = 3
        waited = yield from wait_for_invocations(env, expected_total, max_wait=10.0)
        logger.info(
            "waited %.2f simtime seconds for %d invocations to finish",
            waited, expected_total,
        )

        logger.info("cold start workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_cold_start_deployment()]

    def prepare_cold_start_deployment(self) -> FunctionDeployment:
        """
        准备冷启动函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="200m",
            memory="256Mi",
        )
        container = FunctionContainer(fn_image, resource_config=resource_config)

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 1
        scaling_config.scale_max = 1

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    cold_start 样例入口。
    """
    configure_logging()

    logger.info("creating cold start topology")
    topology = example_topology()

    logger.info("creating cold start benchmark")
    benchmark = ColdStartBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 使用带冷启动阶段探针的函数模拟器。
    sim.create_simulator_factory = ColdStartSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    phase_summary_df = dfs.get("cold_start_phase_summary")
    if phase_summary_df is not None and len(phase_summary_df) > 0:
        logger.info("cold start phase summary:\\n%s", phase_summary_df.to_string(index=False))

    replica_path_df = dfs.get("cold_start_replica_path_summary")
    if replica_path_df is not None and len(replica_path_df) > 0:
        logger.info("cold start replica path summary:\\n%s", replica_path_df.to_string(index=False))

    warm_cold_df = dfs.get("cold_start_warm_cold_compare")
    if warm_cold_df is not None and len(warm_cold_df) > 0:
        logger.info("cold start warm/cold compare:\\n%s", warm_cold_df.to_string(index=False))

    probe_inv_df = dfs.get("cold_start_probe_invocation_join")
    if probe_inv_df is not None and "duration_match" in probe_inv_df.columns:
        all_match = bool(probe_inv_df["duration_match"].all())
        logger.info(
            "probe × invocation join: %d rows, all duration_match=%s",
            len(probe_inv_df), all_match,
        )

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
