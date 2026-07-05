"""
文件作用：论文实验的轻量 trace-driven 模拟器。

该模拟器不直接依赖 faas-sim 核心接口，避免不同源码版本带来的兼容性问题。
它保留论文实验所需的关键变量：
- 函数 warm 实例缓存；
- 镜像缓存；
- 数据缓存；
- R_cache / R_load / R_desired；
- 缓存感知节点选择；
- 请求级延迟估计。
"""

import math
from collections import defaultdict, deque
from copy import deepcopy
from typing import Deque, Dict, List, Set, Tuple

from models import (
    CandidateScore,
    ControlDecision,
    EvictionEvent,
    ExperimentCase,
    FunctionProfile,
    NodeState,
    RequestResult,
    WarmEntry,
    WorkloadEvent,
)


class ThesisExperimentSimulator:
    """
    单个实验 case 的模拟器。
    """

    def __init__(
        self,
        case: ExperimentCase,
        profiles: Dict[str, FunctionProfile],
        nodes: Dict[str, NodeState],
        workload: List[WorkloadEvent],
    ):
        """
        初始化模拟器。
        """
        self.case = case
        self.profiles = profiles
        self.nodes = deepcopy(nodes)
        self.workload = workload

        self.warm_entries: Dict[str, WarmEntry] = {}
        self.image_cache: Set[Tuple[str, str]] = set()
        self.data_cache: Set[Tuple[str, str]] = set()
        self.recent_access: Dict[str, Deque[float]] = defaultdict(deque)
        self.current_replicas: Dict[str, int] = defaultdict(int)
        self.round_robin_cursor = 0

        self.request_results: List[RequestResult] = []
        self.control_decisions: List[ControlDecision] = []
        self.candidate_scores: List[CandidateScore] = []
        self.eviction_events: List[EvictionEvent] = []

    @property
    def cache_used(self) -> int:
        """
        返回当前函数 warm 缓存容量占用。
        """
        return sum(entry.memory_units for entry in self.warm_entries.values())

    def run(self):
        """
        运行单个实验 case。
        """
        for event in self.workload:
            self.handle_event(event)

        return {
            "request_results": self.request_results,
            "control_decisions": self.control_decisions,
            "candidate_scores": self.candidate_scores,
            "eviction_events": self.eviction_events,
        }

    def handle_event(self, event: WorkloadEvent):
        """
        处理单个请求事件。
        """
        self.expire_warm_entries(event.time)
        self.record_access(event.function_name, event.time)

        profile = self.profiles[event.function_name]
        r_cache, r_load, r_desired, utility, control = self.compute_control_decision(event, profile)
        self.control_decisions.append(control)
        self.current_replicas[event.function_name] = r_desired

        selected_node, scores = self.select_node(event, profile)
        self.candidate_scores.extend(scores)

        warm_hit = event.function_name in self.warm_entries
        image_hit = (event.function_name, selected_node.node_name) in self.image_cache
        data_hit = (event.function_name, selected_node.node_name) in self.data_cache

        cold_start_penalty = 0.0 if warm_hit else profile.cold_start_duration
        image_pull_penalty = 0.0 if image_hit else profile.image_pull_duration
        data_fetch_penalty = 0.0 if data_hit else profile.data_fetch_duration
        network_latency = selected_node.network_latency_ms / 1000.0

        latency = (
            profile.warm_duration
            + cold_start_penalty
            + image_pull_penalty
            + data_fetch_penalty
            + network_latency
        )

        self.refresh_runtime_state(event, profile, selected_node, utility)

        self.request_results.append(
            RequestResult(
                case_id=self.case.case_id,
                policy_name=self.case.policy_name,
                request_id=event.request_id,
                time=event.time,
                phase=event.phase,
                function_name=event.function_name,
                source_zone=event.source_zone,
                selected_node=selected_node.node_name,
                warm_hit=warm_hit,
                image_cache_hit=image_hit,
                data_cache_hit=data_hit,
                latency=latency,
                warm_duration=profile.warm_duration,
                cold_start_penalty=cold_start_penalty,
                image_pull_penalty=image_pull_penalty,
                data_fetch_penalty=data_fetch_penalty,
                network_latency=network_latency,
                r_cache=r_cache,
                r_load=r_load,
                r_desired=r_desired,
                cache_utility=utility,
                cache_used_after=self.cache_used,
                warm_keys_after=self.warm_keys_text(),
            )
        )

    def compute_control_decision(self, event: WorkloadEvent, profile: FunctionProfile):
        """
        计算 R_cache、R_load 和 R_desired。
        """
        recent_rate = self.recent_rate(event.function_name)
        cold_benefit = profile.cold_start_duration * (
            0.6 * len(self.recent_access[event.function_name])
            + 2.0 * recent_rate
        )
        resource_cost = max(profile.memory_units, 1) * 0.60
        utility = cold_benefit / max(resource_cost, 1e-9)

        r_cache = 0
        if self.case.use_cache_decision and utility >= self.case.cache_utility_threshold:
            r_cache = 1

        r_load = 0
        if self.case.use_load_scaling and recent_rate > 0:
            effective_capacity = max(profile.replica_capacity_rps * self.case.target_utilization, 1e-9)
            r_load = int(math.ceil(recent_rate / effective_capacity))

        r_desired = max(r_cache, r_load)

        if r_desired > self.current_replicas[event.function_name]:
            action = "scale_out" if r_load >= r_cache else "prewarm"
            reason = "load_requires_more_replicas" if r_load >= r_cache else "cache_requires_warm_replica"
        elif r_desired < self.current_replicas[event.function_name]:
            action = "scale_in"
            reason = "desired_replicas_lower_than_current"
        elif r_cache > 0:
            action = "protect"
            reason = "cache_keeps_replica"
        else:
            action = "observe"
            reason = "no_change"

        control = ControlDecision(
            case_id=self.case.case_id,
            policy_name=self.case.policy_name,
            request_id=event.request_id,
            time=event.time,
            function_name=event.function_name,
            recent_rate=recent_rate,
            cold_benefit=cold_benefit,
            resource_cost=resource_cost,
            cache_utility=utility,
            r_cache=r_cache,
            r_load=r_load,
            r_desired=r_desired,
            current_replicas=self.current_replicas[event.function_name],
            action=action,
            reason=reason,
        )

        return r_cache, r_load, r_desired, utility, control

    def select_node(self, event: WorkloadEvent, profile: FunctionProfile):
        """
        选择目标节点。
        """
        scores = [self.score_node(event, profile, node) for node in self.nodes.values()]
        feasible_scores = [item for item in scores if item.feasible]

        if not feasible_scores:
            raise RuntimeError(f"no feasible node for function={event.function_name}")

        if self.case.use_cache_aware_scheduler:
            selected_score = max(feasible_scores, key=lambda item: item.total_score)
        else:
            feasible_nodes = [self.nodes[item.candidate_node] for item in feasible_scores]
            selected_node = feasible_nodes[self.round_robin_cursor % len(feasible_nodes)]
            self.round_robin_cursor += 1
            selected_score = next(item for item in feasible_scores if item.candidate_node == selected_node.node_name)

        selected_node = self.nodes[selected_score.candidate_node]

        marked_scores = []
        for item in scores:
            item.selected = item.candidate_node == selected_node.node_name
            marked_scores.append(item)

        return selected_node, marked_scores

    def score_node(self, event: WorkloadEvent, profile: FunctionProfile, node: NodeState) -> CandidateScore:
        """
        计算候选节点评分。
        """
        accel_match = (not profile.require_accel) or node.supports_accel
        feasible = (
            accel_match
            and node.cpu_free >= profile.cpu_demand
            and node.memory_free >= profile.memory_demand
        )

        function_hit = self.function_cache_hit(event.function_name, node.node_name)
        image_hit = (event.function_name, node.node_name) in self.image_cache
        data_hit = (event.function_name, node.node_name) in self.data_cache
        zone_match = node.edge_zone == event.source_zone or node.edge_zone == profile.preferred_zone

        if self.case.use_cache_aware_scheduler:
            cache_score = (8.0 if function_hit else 0.0) + (2.0 if image_hit else 0.0) + (2.0 if data_hit else 0.0)
            locality_score = 1.5 if zone_match else 0.0
        else:
            cache_score = 0.0
            locality_score = 0.2 if zone_match else 0.0

        resource_score = 2.0 * min(node.cpu_free, node.memory_free)
        load_penalty = 2.0 * node.current_load
        latency_penalty = node.network_latency_ms / 50.0

        if feasible:
            total_score = cache_score + resource_score + locality_score - load_penalty - latency_penalty
            reason = "cache_aware_score" if self.case.use_cache_aware_scheduler else "round_robin_candidate"
        else:
            total_score = -9999.0
            reason = "infeasible_resource_or_accel"

        return CandidateScore(
            case_id=self.case.case_id,
            policy_name=self.case.policy_name,
            request_id=event.request_id,
            time=event.time,
            function_name=event.function_name,
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
            selected=False,
            reason=reason,
        )

    def refresh_runtime_state(
        self,
        event: WorkloadEvent,
        profile: FunctionProfile,
        selected_node: NodeState,
        utility: float,
    ):
        """
        请求执行后刷新缓存和节点状态。
        """
        keep_alive = self.keep_alive_window(profile, utility)
        self.warm_entries[event.function_name] = WarmEntry(
            function_name=event.function_name,
            node_name=selected_node.node_name,
            memory_units=profile.memory_units,
            expire_time=event.time + keep_alive,
            last_access_time=event.time,
            access_count=self.warm_entries.get(event.function_name, WarmEntry(
                event.function_name,
                selected_node.node_name,
                profile.memory_units,
                event.time,
                event.time,
                0,
                utility,
            )).access_count + 1,
            utility=utility,
        )

        self.image_cache.add((event.function_name, selected_node.node_name))
        self.data_cache.add((event.function_name, selected_node.node_name))

        selected_node.current_load = min(1.0, selected_node.current_load + 0.03)
        selected_node.cpu_free = max(0.0, selected_node.cpu_free - profile.cpu_demand * 0.06)
        selected_node.memory_free = max(0.0, selected_node.memory_free - profile.memory_demand * 0.04)

        self.ensure_cache_capacity(event.time, event.function_name)

    def keep_alive_window(self, profile: FunctionProfile, utility: float) -> float:
        """
        根据策略生成保活窗口。
        """
        if not self.case.use_cache_decision:
            return self.case.base_keep_alive

        window = (
            self.case.base_keep_alive
            + 0.8 * profile.cold_start_duration
            + 0.8 * utility
            - 0.2 * profile.memory_units
        )
        return max(0.5, min(self.case.max_keep_alive, window))

    def expire_warm_entries(self, now: float):
        """
        过期 warm 实例。
        """
        expired = [
            name for name, entry in self.warm_entries.items()
            if entry.expire_time <= now
        ]

        for name in expired:
            entry = self.warm_entries.pop(name)
            self.eviction_events.append(
                EvictionEvent(
                    case_id=self.case.case_id,
                    policy_name=self.case.policy_name,
                    time=now,
                    function_name=name,
                    evicted_function=name,
                    evicted_node=entry.node_name,
                    reason="keep_alive_expired",
                    utility=entry.utility,
                    cache_used_after=self.cache_used,
                )
            )

    def ensure_cache_capacity(self, now: float, function_name: str):
        """
        在容量预算下驱逐低效用缓存项。
        """
        while self.cache_used > self.case.cache_capacity_units and self.warm_entries:
            victim = min(
                self.warm_entries.values(),
                key=lambda entry: (entry.utility, entry.last_access_time),
            )
            removed = self.warm_entries.pop(victim.function_name)
            self.eviction_events.append(
                EvictionEvent(
                    case_id=self.case.case_id,
                    policy_name=self.case.policy_name,
                    time=now,
                    function_name=function_name,
                    evicted_function=removed.function_name,
                    evicted_node=removed.node_name,
                    reason="cache_capacity_pressure",
                    utility=removed.utility,
                    cache_used_after=self.cache_used,
                )
            )

    def function_cache_hit(self, function_name: str, node_name: str) -> bool:
        """
        判断函数 warm 缓存是否命中。
        """
        entry = self.warm_entries.get(function_name)
        return entry is not None and entry.node_name == node_name

    def record_access(self, function_name: str, now: float):
        """
        记录近期访问。
        """
        window = self.recent_access[function_name]
        window.append(now)

        while window and now - window[0] > 5.0:
            window.popleft()

    def recent_rate(self, function_name: str) -> float:
        """
        计算 5 个时间单位内的近期请求速率。
        """
        return len(self.recent_access[function_name]) / 5.0

    def warm_keys_text(self) -> str:
        """
        返回当前 warm 缓存键。
        """
        return ";".join(
            f"{name}@{entry.node_name}"
            for name, entry in sorted(self.warm_entries.items())
        )
