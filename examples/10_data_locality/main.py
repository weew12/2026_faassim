"""
文件作用：faas-sim 数据本地性样例。

本样例演示 StorageIndex、Skippy DataLocalityPriority 和 simulate_data_download() 的协同过程，包括：
- 将对象数据登记到 storage_near；
- 函数通过标签声明需要读取 video-bucket/frame-seq-001；
- 数据本地性感知调度选择更靠近数据的节点；
- 强制远端调度作为对比组；
- 导出数据下载耗时、网络流和调度结果指标；
- 论文 demo 关键摘要 + 数据自检。

运行方式：
    python -u examples/10_data_locality/main.py
    python -u examples/10_data_locality/plot.py
"""

import logging
import sys
from pathlib import Path
from typing import List, Callable

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

from analysis import (
    export_outputs,
    export_comparison,
    data_self_check,
)
from scheduler import (
    InstrumentedDataLocalityScheduler,
    ForcedNodeScheduler,
)
from simulator import DataLocalitySimulatorFactory
from storage import DEFAULT_DATA_OBJECT, build_storage_index
from topology import build_data_locality_topology

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


class DataLocalityBenchmark(Benchmark):
    """
    数据本地性实验 Benchmark。

    该 Benchmark 部署一个需要读取输入数据的函数。
    数据路径通过 FunctionContainer.labels 写入，最终会进入 Pod 标签，
    供 Skippy DataLocalityPriority 和 simulate_data_download() 使用。
    """

    function_name = "data-locality-python-pi"
    image_name = "data-locality-python-pi-cpu"

    def setup(self, env: Environment):
        """
        注册函数镜像。
        """
        containers: docker.ContainerRegistry = env.container_registry

        containers.put(ImageProperties(self.image_name, parse_size_string("48M"), arch="x86"))

        for name, tag_dict in containers.images.items():
            for tag, images in tag_dict.items():
                logger.info("%s, %s, %s", name, tag, images)

    def run(self, env: Environment):
        """
        运行数据本地性实验。
        """
        deployments = self.prepare_deployments()

        for deployment in deployments:
            yield from env.faas.deploy(deployment)

        logger.info("waiting for replica")
        yield env.process(env.faas.poll_available_replica(deployments[0].name))

        logger.info("data locality benchmark finished")

    def prepare_deployments(self) -> List[FunctionDeployment]:
        """
        构造函数部署配置。
        """
        return [self.prepare_data_locality_deployment()]

    def prepare_data_locality_deployment(self) -> FunctionDeployment:
        """
        准备数据本地性函数部署对象。
        """
        fn_image = FunctionImage(image=self.image_name)
        fn = Function(self.function_name, fn_images=[fn_image])

        resource_config = KubernetesResourceConfiguration.create_from_str(
            cpu="200m",
            memory="128Mi",
        )

        data_labels = {
            "data.skippy.io/receives-from-storage": DEFAULT_DATA_OBJECT.size,
            "data.skippy.io/receives-from-storage/path": DEFAULT_DATA_OBJECT.path,
        }

        container = FunctionContainer(
            fn_image,
            resource_config=resource_config,
            labels=data_labels,
        )

        scaling_config = ScalingConfiguration()
        scaling_config.scale_min = 1
        scaling_config.scale_max = 1

        return FunctionDeployment(
            fn,
            [container],
            scaling_config,
        )


def run_scenario(
    scenario_name: str,
    scheduler_factory: Callable[[Environment], object],
    output_dir: Path,
):
    """
    运行一个数据本地性场景。

    每个场景使用独立拓扑、独立 StorageIndex 和独立 Environment，避免状态互相污染。
    """
    logger.info("running data locality scenario: %s", scenario_name)

    network = build_data_locality_topology()
    storage_index = build_storage_index(DEFAULT_DATA_OBJECT)

    env = Environment()
    env.storage_index = storage_index

    benchmark = DataLocalityBenchmark()
    sim = Simulation(network.topology, benchmark, env=env, name=scenario_name)

    sim.create_scheduler = scheduler_factory
    sim.create_simulator_factory = lambda: DataLocalitySimulatorFactory(scenario_name)

    sim.run()

    dfs = export_outputs(sim, scenario_name, output_dir)
    return dfs


def main():
    """
    data_locality 样例入口。
    """
    configure_logging()

    output_dir = Path(__file__).resolve().parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_summaries = []
    candidate_join_dfs = {}

    aware_dfs = run_scenario(
        scenario_name="data_locality_aware",
        scheduler_factory=InstrumentedDataLocalityScheduler.create,
        output_dir=output_dir,
    )
    scenario_summaries.append(aware_dfs["data_locality_summary"])
    candidate_join_dfs["data_locality_aware"] = aware_dfs.get("candidate_vs_actual_join")

    forced_dfs = run_scenario(
        scenario_name="forced_remote",
        scheduler_factory=lambda env: ForcedNodeScheduler.create(env, target_node_name="edge_far"),
        output_dir=output_dir,
    )
    scenario_summaries.append(forced_dfs["data_locality_summary"])
    candidate_join_dfs["forced_remote"] = forced_dfs.get("candidate_vs_actual_join")

    comparison_df = export_comparison(output_dir, scenario_summaries, candidate_join_dfs)

    if comparison_df is not None and len(comparison_df) > 0:
        logger.info("data locality comparison:\n%s", comparison_df.to_string(index=False))

    # 数据自检
    import pandas as _pd
    paper_path = output_dir / "data_locality_paper_highlight.csv"
    paper_df = _pd.read_csv(paper_path) if paper_path.exists() else _pd.DataFrame()

    checks = data_self_check(
        comparison_df=comparison_df,
        paper_df=paper_df,
        candidate_join_aware_df=candidate_join_dfs.get("data_locality_aware", _pd.DataFrame()),
        candidate_join_forced_df=candidate_join_dfs.get("forced_remote", _pd.DataFrame()),
        output_dir=output_dir,
    )
    check_df = _pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "data_locality_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    passed = int(check_df["passed"].sum())
    total = len(check_df)
    logger.info("data self-check: %d / %d PASS", passed, total)
    if passed < total:
        for _, row in check_df[~check_df["passed"]].iterrows():
            logger.warning("  FAILED: %s", row["check_id"])

    # 论文 demo 关键摘要：aware vs forced 的下载时长和理论值
    highlight_path = output_dir / "data_locality_paper_highlight.csv"
    if highlight_path.exists():
        hl = _pd.read_csv(highlight_path)
        speedup_row = hl[hl.metric == "speedup_ratio_forced_over_aware"]
        if not speedup_row.empty:
            logger.info(
                "paper highlight: forced_remote / data_locality_aware speedup = %.1fx",
                float(speedup_row["value"].iloc[0]),
            )

    # 打印 paper_highlight 全表
    if not paper_df.empty:
        logger.info("paper highlight:\n%s", paper_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
