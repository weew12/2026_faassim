"""
文件作用：批量实验配置定义。

该文件集中定义策略、负载、随机种子和实验组合，避免把批量循环参数散落在 main.py 中。
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class WorkloadConfig:
    """
    负载配置。

    字段：
    - name：负载名称；
    - rps：请求速率；
    - max_requests：请求总数。
    """

    name: str
    rps: float
    max_requests: int


@dataclass(frozen=True)
class PolicyConfig:
    """
    策略配置。

    字段：
    - name：策略名称；
    - scheduler：调度器类型，支持 default_skippy / fixed_node；
    """

    name: str
    scheduler: str


@dataclass(frozen=True)
class ExperimentCase:
    """
    单次实验配置。

    字段：
    - case_id：实验编号；
    - policy：策略配置；
    - workload：负载配置；
    - seed：随机种子；
    """

    case_id: str
    policy: PolicyConfig
    workload: WorkloadConfig
    seed: int


@dataclass(frozen=True)
class BatchExperimentConfig:
    """
    批量实验总配置。
    """

    policies: List[PolicyConfig]
    workloads: List[WorkloadConfig]
    seeds: List[int]


def default_batch_config() -> BatchExperimentConfig:
    """
    返回默认批量实验配置。

    默认配置保持较小规模，便于样例快速运行：
    - 2 个策略；
    - 2 个负载；
    - 2 个随机种子；
    - 共 8 次仿真。
    """
    return BatchExperimentConfig(
        policies=[
            PolicyConfig(name="default_skippy", scheduler="default_skippy"),
            PolicyConfig(name="fixed_node", scheduler="fixed_node"),
        ],
        workloads=[
            WorkloadConfig(name="low_load", rps=3, max_requests=12),
            WorkloadConfig(name="medium_load", rps=8, max_requests=24),
        ],
        seeds=[1, 2],
    )


def build_experiment_cases(config: BatchExperimentConfig) -> List[ExperimentCase]:
    """
    根据批量配置生成实验组合。
    """
    cases: List[ExperimentCase] = []

    for policy in config.policies:
        for workload in config.workloads:
            for seed in config.seeds:
                case_id = f"{policy.name}__{workload.name}__seed_{seed}"
                cases.append(
                    ExperimentCase(
                        case_id=case_id,
                        policy=policy,
                        workload=workload,
                        seed=seed,
                    )
                )

    return cases
