"""
文件作用：faas-sim trace-driven / oracle-style 执行时间样例。

本样例演示如何基于 CSV trace 构造函数执行时间 Oracle，包括：
- 读取函数执行时间轨迹；
- 为不同函数维护独立样本序列；
- 函数 invoke 阶段从 trace 中取样；
- 导出实际取样记录和调用结果。

运行方式：
    python -u examples/07_trace_oracle/main.py
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
from simulator import TraceOracleSimulatorFactory

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
    创建 trace_oracle 样例使用的拓扑。

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
    不等待 N 次 invoke 全部跑完。原来的实现用 `env.timeout(2.0)` 硬等待，
    当 trace 的 duration 变大时容易丢请求；这里改成"看到 N 条 invocations 记录"。

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


class TraceOracleBenchmark(Benchmark):
    """
    trace-driven 执行时间实验 Benchmark。

    该 Benchmark 部署两个函数：
    - trace-fast-python-pi：使用短执行时间 trace；
    - trace-slow-python-pi：使用长执行时间 trace。

    两个函数的 invoke 阶段都从同一份 CSV trace 中取样。
    """

    fast_fn_name = "trace-fast-python-pi"
    fast_image_name = "trace-fast-python-pi-cpu"

    slow_fn_name = "trace-slow-python-pi"
    slow_image_name = "trace-slow-python-pi-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        for image_name, size in [
            (self.fast_image_name, "32M"),
            (self.slow_image_name, "48M"),
        ]:
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="arm32"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="x86"))
            containers.put(ImageProperties(image_name, parse_size_string(size), arch="aarch64"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行 trace oracle 实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replicas")
        for deployment in deployments:
            yield env.process(env.faas.poll_available_replica(deployment.name))

        logger.info("triggering trace oracle workload")

        fast_ia = static_arrival_profile(constant_rps_profile(rps=8))
        slow_ia = static_arrival_profile(constant_rps_profile(rps=5))

        yield from function_trigger(
            env,
            deployments[0],
            fast_ia,
            max_requests=16,
        )

        yield from function_trigger(
            env,
            deployments[1],
            slow_ia,
            max_requests=12,
        )

        # 等所有 invoke 进程完成。
        # function_trigger(max_requests=N) 只保证触发 N 个请求就返回，
        # 不等待 N 次 invoke 全部跑完。这里轮询 sim.env.metrics.records 直到
        # invocations 数达到 16+12=28，或最多等 30 simtime 秒，避免 trace 变慢时丢请求。
        expected_total = 16 + 12
        waited = yield from wait_for_invocations(env, expected_total, max_wait=30.0)
        logger.info(
            "waited %.2f simtime seconds for %d invocations to finish",
            waited, expected_total,
        )

        logger.info("trace oracle workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [
            self.prepare_deployment(self.fast_fn_name, self.fast_image_name, cpu="100m", memory="128Mi"),
            self.prepare_deployment(self.slow_fn_name, self.slow_image_name, cpu="200m", memory="256Mi"),
        ]

    def prepare_deployment(self, function_name: str, image_name: str, cpu: str, memory: str) -> FunctionDeployment:
        """
        创建函数部署对象。
        """
        fn_image = FunctionImage(image=image_name)
        fn = Function(function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu=cpu,
            memory=memory,
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
    trace_oracle 样例入口。
    """
    configure_logging()

    root_dir = Path(__file__).resolve().parent
    trace_path = root_dir / "traces" / "function_runtime_trace.csv"

    logger.info("using trace file: %s", trace_path)

    logger.info("creating trace oracle topology")
    topology = example_topology()

    logger.info("creating trace oracle benchmark")
    benchmark = TraceOracleBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 使用 trace-driven 函数执行时间模拟器。
    sim.create_simulator_factory = lambda: TraceOracleSimulatorFactory(trace_path)

    logger.info("running simulation")
    sim.run()

    output_dir = root_dir / "outputs"
    dfs = export_outputs(sim, output_dir, trace_path)

    trace_input_summary_df = dfs.get("trace_input_summary")
    if trace_input_summary_df is not None and len(trace_input_summary_df) > 0:
        logger.info("trace input summary:\\n%s", trace_input_summary_df.to_string(index=False))

    trace_sample_summary_df = dfs.get("trace_sample_summary")
    if trace_sample_summary_df is not None and len(trace_sample_summary_df) > 0:
        logger.info("trace sample summary:\\n%s", trace_sample_summary_df.to_string(index=False))

    trace_cycle_df = dfs.get("trace_cycle_summary")
    if trace_cycle_df is not None and len(trace_cycle_df) > 0:
        logger.info("trace cycle summary:\\n%s", trace_cycle_df.to_string(index=False))

    trace_join_df = dfs.get("trace_invoke_sample_join")
    if trace_join_df is not None and len(trace_join_df) > 0:
        all_match = bool(trace_join_df["duration_match"].all())
        logger.info(
            "trace invoke sample join: %d rows, all duration_match=%s",
            len(trace_join_df), all_match,
        )

    invocation_summary_df = dfs.get("trace_invocation_summary")
    if invocation_summary_df is not None and len(invocation_summary_df) > 0:
        logger.info("trace invocation summary:\\n%s", invocation_summary_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
