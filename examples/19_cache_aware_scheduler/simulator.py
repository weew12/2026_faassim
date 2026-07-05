"""
文件作用：cache_aware_scheduler 样例使用的函数生命周期模拟器。

该模拟器在 invoke 阶段根据调度节点是否存在目标函数 warm 缓存，区分 cache hit 和 cache miss，
并记录请求级执行结果。
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

from cache_state import CacheStateIndex

logger = logging.getLogger(__name__)


class CacheAwareSimulatorFactory(SimulatorFactory):
    """
    缓存感知调度样例的函数模拟器工厂。
    """

    def __init__(self, scenario_name: str, cache_index: CacheStateIndex):
        """
        初始化工厂。
        """
        self.scenario_name = scenario_name
        self.cache_index = cache_index

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return CacheAwareFunctionSimulator(self.scenario_name, self.cache_index)


class CacheAwareFunctionSimulator(FunctionSimulator):
    """
    缓存感知函数生命周期模拟器。
    """

    def __init__(self, scenario_name: str, cache_index: CacheStateIndex):
        """
        初始化函数模拟器。
        """
        self.scenario_name = scenario_name
        self.cache_index = cache_index
        self.warm_duration = 0.10
        self.default_cold_start = 1.00

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，包含镜像拉取。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        yield env.timeout(0.10)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段。
        """
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用，并根据缓存状态计算延迟。
        """
        function_name = replica.function.name
        node_name = replica.node.name

        entry = self.cache_index.entry_for_node(function_name, node_name)
        cache_hit = entry is not None

        cold_start_penalty = 0.0
        if cache_hit:
            final_duration = self.warm_duration
            avg_cold_start = entry.avg_cold_start
        else:
            avg_cold_start = self._avg_cold_start_for_function(function_name)
            cold_start_penalty = avg_cold_start
            final_duration = self.warm_duration + cold_start_penalty

        logger.info(
            "[simtime=%.2f] cache-aware invoke scenario=%s request=%s function=%s node=%s cache_hit=%s duration=%.3f",
            env.now,
            self.scenario_name,
            request.request_id,
            function_name,
            node_name,
            cache_hit,
            final_duration,
        )

        env.metrics.log(
            "cache_aware_request_probe",
            {
                "cache_hit": cache_hit,
                "warm_duration": self.warm_duration,
                "cold_start_penalty": cold_start_penalty,
                "final_duration": final_duration,
                "avg_cold_start": avg_cold_start,
            },
            scenario=self.scenario_name,
            function_name=function_name,
            request_id=request.request_id,
            node_name=node_name,
            replica_id=id(replica),
        )

        cpu_millis = replica.node.capacity.cpu_millis * 0.10
        replica.node.current_requests.add(request)
        env.resource_state.put_resource(replica, "cpu", cpu_millis)

        yield env.timeout(final_duration)

        env.resource_state.remove_resource(replica, "cpu", cpu_millis)
        replica.node.current_requests.remove(request)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)

    def _avg_cold_start_for_function(self, function_name: str) -> float:
        """
        查询函数平均冷启动时间。
        """
        entries = self.cache_index.entries_for_function(function_name)
        if entries:
            return entries[0].avg_cold_start
        return self.default_cold_start
