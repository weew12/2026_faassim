"""
文件作用：边缘缓存感知调度实验执行器。
"""

from copy import deepcopy
from typing import Dict, List

import pandas as pd

from cache_index import EdgeCacheIndex
from models import CacheEntry, FunctionProfile, NodeState, RequestEvent
from scheduler import EdgeCacheAwareScheduler, EdgeRoundRobinScheduler


class EdgeCacheSchedulerRunner:
    """
    调度实验执行器。
    """

    def __init__(
        self,
        nodes: Dict[str, NodeState],
        profiles: Dict[str, FunctionProfile],
        cache_entries: List[CacheEntry],
        requests: List[RequestEvent],
    ):
        """
        初始化执行器。
        """
        self.nodes = nodes
        self.profiles = profiles
        self.cache_entries = cache_entries
        self.requests = requests

    def run(self):
        """
        运行两个调度策略并返回结果。
        """
        policy_outputs = []

        for scheduler in self._build_schedulers():
            results = []
            candidate_scores = []

            for request in self.requests:
                result, scores = scheduler.schedule(request)
                results.append(result)
                candidate_scores.extend(scores)

            policy_outputs.append(
                {
                    "scheduler": scheduler.policy_name,
                    "results": results,
                    "candidate_scores": candidate_scores,
                }
            )

        result_rows = []
        candidate_rows = []

        for output in policy_outputs:
            result_rows.extend([item.__dict__ for item in output["results"]])
            candidate_rows.extend([item.__dict__ for item in output["candidate_scores"]])

        return {
            "edge_cache_scheduling_result": pd.DataFrame(result_rows),
            "edge_cache_candidate_score": pd.DataFrame(candidate_rows),
        }

    def _build_schedulers(self):
        """
        创建策略实例。

        每个策略使用独立节点状态和缓存索引，避免运行时缓存演化互相影响。
        """
        return [
            EdgeRoundRobinScheduler(
                nodes=deepcopy(self.nodes),
                profiles=self.profiles,
                cache_index=EdgeCacheIndex(self.cache_entries),
            ),
            EdgeCacheAwareScheduler(
                nodes=deepcopy(self.nodes),
                profiles=self.profiles,
                cache_index=EdgeCacheIndex(self.cache_entries),
            ),
        ]
