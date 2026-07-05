"""
文件作用：缓存策略实验执行器。

该文件负责把请求 trace 依次送入缓存策略，并记录请求结果、驱逐事件和缓存状态。
"""

from typing import Dict, List

import pandas as pd

from cache_model import (
    RequestResult,
    EvictionEvent,
    CacheStateRecord,
)
from function_catalog import FunctionSpec
from policies import CachePolicy
from workload import FunctionRequest


class CachePolicyExperimentRunner:
    """
    缓存策略实验执行器。
    """

    def __init__(
        self,
        catalog: Dict[str, FunctionSpec],
        requests: List[FunctionRequest],
        policies: List[CachePolicy],
    ):
        """
        初始化执行器。
        """
        self.catalog = catalog
        self.requests = requests
        self.policies = policies

    def run(self) -> Dict[str, pd.DataFrame]:
        """
        运行全部缓存策略。
        """
        all_request_results: List[RequestResult] = []
        all_evictions: List[EvictionEvent] = []
        all_cache_states: List[CacheStateRecord] = []

        for policy in self.policies:
            request_results, evictions, states = self.run_policy(policy)
            all_request_results.extend(request_results)
            all_evictions.extend(evictions)
            all_cache_states.extend(states)

        return {
            "cache_request_result": pd.DataFrame([item.__dict__ for item in all_request_results]),
            "cache_eviction": pd.DataFrame([item.__dict__ for item in all_evictions]),
            "cache_state": pd.DataFrame([item.__dict__ for item in all_cache_states]),
        }

    def run_policy(self, policy: CachePolicy):
        """
        运行单个缓存策略。
        """
        request_results: List[RequestResult] = []
        evictions: List[EvictionEvent] = []
        states: List[CacheStateRecord] = []

        for request in self.requests:
            spec = self.catalog[request.function_name]
            used_before = policy.cache.used_units

            cache_hit, current_evictions = policy.on_request(request)

            latency = spec.warm_duration
            cold_start_penalty = 0.0
            if not cache_hit:
                cold_start_penalty = spec.cold_start_duration
                latency += cold_start_penalty

            evictions.extend(current_evictions)

            request_results.append(
                RequestResult(
                    policy_name=policy.name,
                    request_id=request.request_id,
                    time=request.time,
                    function_name=request.function_name,
                    cache_hit=cache_hit,
                    latency=latency,
                    cold_start_penalty=cold_start_penalty,
                    cache_used_before=used_before,
                    cache_used_after=policy.cache.used_units,
                    cache_keys_after=policy.cache.keys_text(),
                )
            )

            states.append(
                CacheStateRecord(
                    policy_name=policy.name,
                    time=request.time,
                    request_id=request.request_id,
                    function_name=request.function_name,
                    cache_used=policy.cache.used_units,
                    cache_capacity=policy.cache.capacity_units,
                    cache_keys=policy.cache.keys_text(),
                )
            )

        return request_results, evictions, states
