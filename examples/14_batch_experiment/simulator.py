"""
文件作用：batch_experiment 样例使用的函数生命周期模拟器。

该模拟器为每个实验 case 生成可复现的执行时间扰动，使 seed 在批量实验中具有实际意义。
"""

import logging
import random

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
)

from experiment_config import ExperimentCase

logger = logging.getLogger(__name__)


class BatchExperimentSimulatorFactory(SimulatorFactory):
    """
    批量实验函数模拟器工厂。
    """

    def __init__(self, case: ExperimentCase):
        """
        初始化工厂。

        每个 case 使用独立随机数生成器，保证相同 seed 可复现。
        """
        self.case = case
        self.rng = random.Random(case.seed)

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return BatchExperimentFunctionSimulator(
            case=self.case,
            rng=self.rng,
        )


class BatchExperimentFunctionSimulator(FunctionSimulator):
    """
    批量实验函数生命周期模拟器。

    执行时间由基础耗时和少量随机扰动组成：
    - low_load / medium_load 使用同一执行模型；
    - seed 控制扰动序列；
    - 每次请求记录 batch_invoke_probe，便于复核结果。
    """

    def __init__(self, case: ExperimentCase, rng: random.Random):
        """
        初始化函数模拟器。
        """
        self.case = case
        self.rng = rng

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，包含镜像拉取。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        yield env.timeout(0.2)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        关键探针（沿用 02-13 的 invoke_dispatch_probe 模式）：
        入口 simtime + replica_id + request_id + expected_t_exec（按 batch_invoke
        真实派发值）一并写两条探针（dispatch_probe + batch_invoke_probe），
        便于 probe×invocation join 自洽检查（虽然 14 的 simulator 已经有
        batch_invoke_probe，但 invoke_dispatch_probe 提供更简洁的 join 接口）。
        """
        base_duration = 0.18
        jitter = self.rng.uniform(0.0, 0.08)
        duration = base_duration + jitter

        # 派发探针（沿用 02-13 模式）：simtime + replica_id + request_id + expected_t_exec
        env.metrics.log(
            "invoke_dispatch_probe",
            {
                "simtime": float(env.now),
                "replica_id": id(replica),
                "request_id": request.request_id,
                "expected_t_exec": float(duration),
            },
            case_id=self.case.case_id,
            policy=self.case.policy.name,
            workload=self.case.workload.name,
            function_name=replica.function.name,
            node=replica.node.name,
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.12

        logger.debug(
            "[simtime=%.2f] batch invoke case=%s request=%s duration=%.4f",
            env.now,
            self.case.case_id,
            request.request_id,
            duration,
        )

        env.metrics.log(
            "batch_invoke_probe",
            {
                "base_duration": base_duration,
                "jitter": jitter,
                "duration": duration,
                "seed": self.case.seed,
                "rps": self.case.workload.rps,
            },
            case_id=self.case.case_id,
            policy=self.case.policy.name,
            workload=self.case.workload.name,
            function_name=replica.function.name,
            node_name=replica.node.name,
            request_id=request.request_id,
        )

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        replica.node.current_requests.add(request)

        yield env.timeout(duration)

        replica.node.current_requests.remove(request)
        env.resource_state.remove_resource(replica, "cpu", cpu_millis)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
