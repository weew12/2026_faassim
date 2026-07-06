"""
文件作用：faas-sim 原生自动伸缩样例。

本样例演示如何使用 faas-sim 原生自动伸缩相关能力，包括：
- ScalingConfiguration；
- DefaultFaasSystem(scale_by_average_requests=True)；
- 固定 RPS 请求生成器；
- 自动伸缩指标导出；
- 副本数量时间线与摘要结果保存。

运行方式：
    python -u examples/01_autoscaling/main.py
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
from sim.requestgen import function_trigger, constant_rps_profile, expovariate_arrival_profile
from sim.topology import Topology

from analysis import export_outputs
from simulator import AutoscalingSimulatorFactory
from system import create_autoscaling_faas_system

logger = logging.getLogger(__name__)


def configure_logging():
    """
    配置日志输出。

    命令行运行时可以直接看到 faas-sim 内部日志。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def example_topology() -> Topology:
    """
    创建自动伸缩样例使用的拓扑。

    当前复用 UrbanSensingScenario，保持与官方示例风格一致。
    """
    topology = Topology()
    scenario.UrbanSensingScenario().materialize(topology)
    topology.init_docker_registry()
    return topology


class AutoscalingBenchmark(Benchmark):
    """
    自动伸缩实验 Benchmark。

    该 Benchmark 部署一个函数 autoscale-python-pi，
    然后用固定平均 RPS 的请求生成器持续触发请求，
    使原生自动伸缩逻辑能够观察负载并调整副本数量。
    """

    function_name = "autoscale-python-pi"
    image_name = "autoscale-python-pi-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。

        自动伸缩样例使用一个小型 CPU 函数镜像，并为 arm32、x86、aarch64
        三种架构注册镜像，避免调度到不同节点时出现镜像架构缺失。
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
        运行自动伸缩实验。

        流程：
        1. 准备函数部署；
        2. 部署函数；
        3. 等待至少一个副本可用；
        4. 使用请求生成器持续触发函数调用；
        5. 在请求负载下让自动伸缩逻辑产生 scale 指标。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(self.function_name))

        logger.info("triggering autoscaling workload")
        ia_generator = expovariate_arrival_profile(constant_rps_profile(rps=40))

        yield from function_trigger(
            env,
            deployments[0],
            ia_generator,
            max_requests=2000,
        )

        # 等所有 invoke 进程完成。
        # function_trigger(max_requests=N) 只保证触发 N 个请求就返回，
        # 不等待 N 次 invoke 全部跑完。仿真本身已经跑了约 50s 让 2000 个
        # 请求自然完成；这里再加 1s 缓冲确保最后几个 invoke 落盘。
        yield env.timeout(1.0)

        logger.info("autoscaling workload finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_autoscale_python_pi_deployment()]

    def prepare_autoscale_python_pi_deployment(self) -> FunctionDeployment:
        """
        准备自动伸缩函数部署对象。

        scale_min=1 表示至少保留一个副本；
        scale_max=8 表示最多扩展到 8 个副本；
        target_average_rps 用于原生平均请求负载伸缩逻辑。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        container = FunctionContainer(fn_image)

        # 设置基础资源请求，便于调度器和资源监控读取。
        # 当前 faas-sim 版本的 KubernetesResourceConfiguration 只接收 requests，
        # 不支持 Kubernetes 原生 limits 字段，因此这里使用 create_from_str 构造资源请求。
        container.resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="100m",
            memory="128Mi",
        )

        # 当前 faas-sim 版本的 ScalingConfiguration 没有自定义 __init__，
        # 需要先创建对象，再逐项写入伸缩参数。
        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 1
        scaling_config.scale_max = 8
        scaling_config.alert_window = 2
        scaling_config.target_average_rps = 4
        scaling_config.target_average_rps_threshold = 0.05

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def main():
    """
    自动伸缩样例入口。
    """
    configure_logging()

    logger.info("creating autoscaling topology")
    topology = example_topology()

    logger.info("creating autoscaling benchmark")
    benchmark = AutoscalingBenchmark()

    logger.info("creating simulation")
    sim = Simulation(topology, benchmark)

    # 启用原生自动伸缩系统。
    sim.create_faas_system = create_autoscaling_faas_system

    # 使用稳定的函数执行时间模拟器，便于观察负载与副本数量变化。
    sim.create_simulator_factory = AutoscalingSimulatorFactory

    logger.info("running simulation")
    sim.run()

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(sim, output_dir)

    summary_df = dfs.get("autoscaling_summary")
    if summary_df is not None:
        logger.info("autoscaling summary:\n%s", summary_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
