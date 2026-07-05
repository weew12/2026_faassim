"""
文件作用：cold_start 样例使用的函数生命周期模拟器。

该模拟器在 deploy/startup/setup/invoke 阶段分别记录 cold_start_probe 指标，
从而把一次函数副本启动过程拆成可分析的冷启动路径。
"""

import logging
from collections import defaultdict

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
)

from cold_start_model import ColdStartModel

logger = logging.getLogger(__name__)


class ColdStartSimulatorFactory(SimulatorFactory):
    """
    cold_start 样例的函数模拟器工厂。
    """

    def __init__(self):
        """
        初始化模拟器工厂。
        """
        self.model = ColdStartModel()

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return ColdStartFunctionSimulator(self.model)


class ColdStartFunctionSimulator(FunctionSimulator):
    """
    冷启动函数生命周期模拟器。

    样例重点：
    - deploy 阶段调用 docker.pull()，记录镜像拉取/部署耗时；
    - startup 阶段模拟容器运行时启动；
    - setup 阶段模拟业务初始化；
    - invoke 阶段区分 first_invoke 与 warm_invoke；
    - 每个阶段都写入 cold_start_probe，便于汇总冷启动路径。
    """

    # 记录每个副本是否已经处理过首次请求。
    first_invoke_seen = defaultdict(bool)

    def __init__(self, model: ColdStartModel):
        """
        初始化函数模拟器。
        """
        self.model = model

    def _log_phase(self, env: Environment, replica: FunctionReplica, phase: str, started: float, finished: float, **extra):
        """
        记录冷启动阶段事件。
        """
        payload = {
            "phase_duration": finished - started,
            "phase_start": started,
            "phase_finish": finished,
        }
        payload.update(extra)

        env.metrics.log(
            "cold_start_probe",
            payload,
            function_name=replica.function.name,
            image=replica.image,
            node_name=replica.node.name if replica.node is not None else None,
            replica_id=id(replica),
            phase=phase,
        )

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟 deploy 阶段。

        deploy 阶段调用 docker.pull()，因此会包含镜像首次拉取或镜像缓存命中的差异。
        """
        started = env.now

        logger.info(
            "[simtime=%.2f] cold phase deploy begin function=%s image=%s node=%s",
            env.now,
            replica.function.name,
            replica.image,
            replica.node.name,
        )

        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

        finished = env.now

        logger.info(
            "[simtime=%.2f] cold phase deploy finish function=%s duration=%.4f",
            env.now,
            replica.function.name,
            finished - started,
        )

        self._log_phase(env, replica, "deploy", started, finished)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟 startup 阶段。
        """
        config = self.model.get_config(replica.function.name)
        started = env.now

        logger.info(
            "[simtime=%.2f] cold phase startup begin function=%s node=%s duration=%.4f",
            env.now,
            replica.function.name,
            replica.node.name,
            config.startup_duration,
        )

        yield env.timeout(config.startup_duration)

        finished = env.now

        logger.info(
            "[simtime=%.2f] cold phase startup finish function=%s duration=%.4f",
            env.now,
            replica.function.name,
            finished - started,
        )

        self._log_phase(env, replica, "startup", started, finished)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟 setup 阶段。
        """
        config = self.model.get_config(replica.function.name)
        started = env.now

        logger.info(
            "[simtime=%.2f] cold phase setup begin function=%s node=%s duration=%.4f",
            env.now,
            replica.function.name,
            replica.node.name,
            config.setup_duration,
        )

        yield env.timeout(config.setup_duration)

        finished = env.now

        logger.info(
            "[simtime=%.2f] cold phase setup finish function=%s duration=%.4f",
            env.now,
            replica.function.name,
            finished - started,
        )

        self._log_phase(env, replica, "setup", started, finished)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟函数调用阶段。

        对同一副本：
        - 第一次 invoke 记为 first_invoke；
        - 后续 invoke 记为 warm_invoke。
        """
        config = self.model.get_config(replica.function.name)
        replica_key = id(replica)

        if not self.first_invoke_seen[replica_key]:
            phase = "first_invoke"
            duration = config.first_invoke_duration
            self.first_invoke_seen[replica_key] = True
        else:
            phase = "warm_invoke"
            duration = config.warm_invoke_duration

        started = env.now

        logger.info(
            "[simtime=%.2f] %s request=%s function=%s node=%s duration=%.4f",
            env.now,
            phase,
            request.request_id,
            replica.function.name,
            replica.node.name,
            duration,
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.1
        replica.node.current_requests.add(request)
        env.resource_state.put_resource(replica, "cpu", cpu_millis)

        yield env.timeout(duration)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        replica.node.current_requests.remove(request)

        finished = env.now

        self._log_phase(
            env,
            replica,
            phase,
            started,
            finished,
            request_id=request.request_id,
        )

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
