"""
文件作用：边缘缓存感知调度器。

本文件实现两个调度策略：
- EdgeRoundRobinScheduler：缓存无感知基线；
- EdgeCacheAwareScheduler：综合函数缓存、镜像缓存、数据缓存、边缘区域和节点负载评分。
"""

from copy import deepcopy
from typing import Dict, List, Tuple

from cache_index import EdgeCacheIndex
from models import (
    CandidateScore,
    FunctionProfile,
    NodeState,
    RequestEvent,
    SchedulingResult,
)


class EdgeRoundRobinScheduler:
    """
    缓存无感知 round-robin 调度器。
    """

    def __init__(
        self,
        nodes: Dict[str, NodeState],
        profiles: Dict[str, FunctionProfile],
        cache_index: EdgeCacheIndex,
    ):
        """
        初始化调度器。
        """
        self.policy_name = "edge_round_robin"
        self.nodes = deepcopy(nodes)
        self.profiles = profiles
        self.cache_index = cache_index
        self.cursor = 0

    def schedule(self, request: RequestEvent) -> Tuple[SchedulingResult, List[CandidateScore]]:
        """
        调度单个请求。
        """
        profile = self.profiles[request.function_name]
        candidates = [node for node in self.nodes.values() if self._feasible(node, profile)]

        if not candidates:
            raise RuntimeError(f"no feasible node for function={request.function_name}")

        selected = candidates[self.cursor % len(candidates)]
        self.cursor += 1

        scores = [
            self._candidate_score(request, node, selected.node_name == node.node_name)
            for node in self.nodes.values()
        ]

        result = self._build_result(request, selected, total_score=0.0, reason="round_robin")
        self._update_runtime_state(request, selected)

        return result, scores

    def _feasible(self, node: NodeState, profile: FunctionProfile) -> bool:
        """
        判断节点是否满足资源和能力约束。
        """
        if profile.require_accel and not node.supports_accel:
            return False
        if node.cpu_free < profile.cpu_demand:
            return False
        if node.memory_free < profile.memory_demand:
            return False
        return True

    def _candidate_score(self, request: RequestEvent, node: NodeState, selected: bool) -> CandidateScore:
        """
        生成基线候选记录。
        """
        profile = self.profiles[request.function_name]
        feasible = self._feasible(node, profile)
        function_hit = self.cache_index.has("function", request.function_name, node.node_name)
        image_hit = self.cache_index.has("image", request.function_name, node.node_name)
        data_hit = self.cache_index.has("data", request.function_name, node.node_name)
        zone_match = node.edge_zone == request.source_zone or node.edge_zone == profile.preferred_zone
        accel_match = (not profile.require_accel) or node.supports_accel

        return CandidateScore(
            policy_name=self.policy_name,
            request_id=request.request_id,
            time=request.time,
            function_name=request.function_name,
            candidate_node=node.node_name,
            feasible=feasible,
            function_cache_hit=function_hit,
            image_cache_hit=image_hit,
            data_cache_hit=data_hit,
            zone_match=zone_match,
            accel_match=accel_match,
            resource_score=0.0,
            cache_score=0.0,
            locality_score=0.0,
            load_penalty=node.current_load,
            latency_penalty=node.network_latency_ms / 100.0,
            total_score=1.0 if selected else 0.0,
            reason="selected_by_round_robin" if selected else "baseline_candidate",
        )

    def _build_result(self, request: RequestEvent, selected: NodeState, total_score: float, reason: str) -> SchedulingResult:
        """
        根据节点缓存命中情况生成请求级结果。
        """
        profile = self.profiles[request.function_name]
        function_hit = self.cache_index.has("function", request.function_name, selected.node_name)
        image_hit = self.cache_index.has("image", request.function_name, selected.node_name)
        data_hit = self.cache_index.has("data", request.function_name, selected.node_name)

        cold_start_penalty = 0.0 if function_hit else profile.cold_start_duration
        image_pull_penalty = 0.0 if image_hit else profile.image_pull_duration
        data_fetch_penalty = 0.0 if data_hit else profile.data_fetch_duration
        network_latency = selected.network_latency_ms / 1000.0

        estimated_latency = (
            profile.warm_duration
            + cold_start_penalty
            + image_pull_penalty
            + data_fetch_penalty
            + network_latency
        )

        return SchedulingResult(
            policy_name=self.policy_name,
            request_id=request.request_id,
            time=request.time,
            function_name=request.function_name,
            source_zone=request.source_zone,
            selected_node=selected.node_name,
            function_cache_hit=function_hit,
            image_cache_hit=image_hit,
            data_cache_hit=data_hit,
            estimated_latency=estimated_latency,
            cold_start_penalty=cold_start_penalty,
            image_pull_penalty=image_pull_penalty,
            data_fetch_penalty=data_fetch_penalty,
            network_latency=network_latency,
            total_score=total_score,
            reason=reason,
        )

    def _update_runtime_state(self, request: RequestEvent, selected: NodeState):
        """
        请求执行后刷新节点负载与缓存状态。
        """
        profile = self.profiles[request.function_name]
        selected.current_load = min(1.0, selected.current_load + 0.04)
        selected.cpu_free = max(0.0, selected.cpu_free - profile.cpu_demand * 0.10)
        selected.memory_free = max(0.0, selected.memory_free - profile.memory_demand * 0.05)

        self.cache_index.warm_function(request.function_name, selected.node_name)
        self.cache_index.cache_image_and_data(request.function_name, selected.node_name)


class EdgeCacheAwareScheduler(EdgeRoundRobinScheduler):
    """
    边缘缓存感知调度器。
    """

    def __init__(
        self,
        nodes: Dict[str, NodeState],
        profiles: Dict[str, FunctionProfile],
        cache_index: EdgeCacheIndex,
    ):
        """
        初始化调度器。
        """
        super().__init__(nodes, profiles, cache_index)
        self.policy_name = "edge_cache_aware"

    def schedule(self, request: RequestEvent) -> Tuple[SchedulingResult, List[CandidateScore]]:
        """
        调度单个请求。
        """
        scores = [
            self._score_node(request, node)
            for node in self.nodes.values()
        ]

        feasible_scores = [item for item in scores if item.feasible]
        if not feasible_scores:
            raise RuntimeError(f"no feasible node for function={request.function_name}")

        selected_score = max(feasible_scores, key=lambda item: item.total_score)
        selected = self.nodes[selected_score.candidate_node]

        result = self._build_result(
            request=request,
            selected=selected,
            total_score=selected_score.total_score,
            reason=selected_score.reason,
        )
        self._update_runtime_state(request, selected)

        return result, scores

    def _score_node(self, request: RequestEvent, node: NodeState) -> CandidateScore:
        """
        计算候选节点综合得分。
        """
        profile = self.profiles[request.function_name]
        feasible = self._feasible(node, profile)

        function_hit = self.cache_index.has("function", request.function_name, node.node_name)
        image_hit = self.cache_index.has("image", request.function_name, node.node_name)
        data_hit = self.cache_index.has("data", request.function_name, node.node_name)
        zone_match = node.edge_zone == request.source_zone or node.edge_zone == profile.preferred_zone
        accel_match = (not profile.require_accel) or node.supports_accel

        function_score = 8.0 * self.cache_index.freshness("function", request.function_name, node.node_name)
        image_score = 2.0 * self.cache_index.freshness("image", request.function_name, node.node_name)
        data_score = 2.0 * self.cache_index.freshness("data", request.function_name, node.node_name)
        cache_score = function_score + image_score + data_score

        resource_score = 2.0 * min(node.cpu_free, node.memory_free)
        locality_score = 1.5 if zone_match else 0.0
        if node.edge_zone == "cloud":
            locality_score -= 1.0

        load_penalty = 2.0 * node.current_load
        latency_penalty = node.network_latency_ms / 50.0

        if feasible:
            total_score = cache_score + resource_score + locality_score - load_penalty - latency_penalty
            reason = "cache_locality_resource_score"
        else:
            total_score = -9999.0
            reason = "infeasible_resource_or_accel"

        return CandidateScore(
            policy_name=self.policy_name,
            request_id=request.request_id,
            time=request.time,
            function_name=request.function_name,
            candidate_node=node.node_name,
            feasible=feasible,
            function_cache_hit=function_hit,
            image_cache_hit=image_hit,
            data_cache_hit=data_hit,
            zone_match=zone_match,
            accel_match=accel_match,
            resource_score=resource_score,
            cache_score=cache_score,
            locality_score=locality_score,
            load_penalty=load_penalty,
            latency_penalty=latency_penalty,
            total_score=total_score,
            reason=reason,
        )
