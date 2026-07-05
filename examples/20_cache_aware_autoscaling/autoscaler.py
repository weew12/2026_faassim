"""
文件作用：缓存状态感知扩缩容核心逻辑。

本文件实现 R_cache、R_load 和 R_desired 的组合计算：

R_desired = max(R_cache, R_load)

其中：
- R_cache 表示由函数实例缓存收益驱动的保护或预热副本需求；
- R_load 表示由当前请求负载驱动的运行副本需求；
- R_desired 表示最终目标副本数。
"""

import math
from collections import defaultdict
from typing import Dict, List

from models import (
    AutoscalingConfig,
    AutoscalingDecision,
    ControlPlan,
    FunctionState,
)


class CacheAwareAutoscaler:
    """
    缓存状态感知扩缩容器。
    """

    def __init__(self, config: AutoscalingConfig):
        """
        初始化扩缩容器。
        """
        self.config = config

    def evaluate(self, states: List[FunctionState]) -> List[AutoscalingDecision]:
        """
        计算所有时间点和函数的扩缩容决策。
        """
        grouped: Dict[float, List[FunctionState]] = defaultdict(list)
        for state in states:
            grouped[state.time].append(state)

        decisions: List[AutoscalingDecision] = []

        for time_value in sorted(grouped):
            time_decisions = [self._evaluate_one(state) for state in grouped[time_value]]
            time_decisions = self._apply_cache_budget(time_decisions)
            decisions.extend(sorted(time_decisions, key=lambda item: item.function_name))

        return decisions

    def _evaluate_one(self, state: FunctionState) -> AutoscalingDecision:
        """
        计算单个函数状态的扩缩容决策。
        """
        cold_benefit = self._cold_benefit(state)
        resource_cost = self._resource_cost(state)
        cache_utility = cold_benefit / max(resource_cost, self.config.epsilon)

        r_cache_raw = self._r_cache_raw(state, cache_utility)
        r_load_raw = self._r_load_raw(state)

        r_cache = self._clamp_replicas(r_cache_raw)
        r_load = self._clamp_replicas(r_load_raw)

        r_desired_before_budget = max(r_cache, r_load)
        r_desired = self._clamp_replicas(r_desired_before_budget)

        delta = r_desired - state.current_replicas
        action, reason = self._classify_action(state, r_cache, r_load, r_desired, cache_utility)

        return AutoscalingDecision(
            time=state.time,
            function_name=state.function_name,
            current_replicas=state.current_replicas,
            warm_replicas=state.warm_replicas,
            request_rate=state.request_rate,
            n_req=state.n_req,
            avg_cold_start=state.avg_cold_start,
            memory_units=state.memory_units,
            in_flight_requests=state.in_flight_requests,
            last_seen_age=state.last_seen_age,
            cold_benefit=cold_benefit,
            resource_cost=resource_cost,
            cache_utility=cache_utility,
            r_cache_raw=r_cache_raw,
            r_cache=r_cache,
            r_load_raw=r_load_raw,
            r_load=r_load,
            r_desired_before_budget=r_desired_before_budget,
            r_desired=r_desired,
            delta=delta,
            action=action,
            reason=reason,
            selected_by_cache_budget=False,
            capacity_status="not_checked",
        )

    def _cold_benefit(self, state: FunctionState) -> float:
        """
        计算缓存冷启动收益。

        最小样例公式：

        cold_benefit = avg_cold_start * (0.6 * n_req + 1.5 * cold_miss_count + 2.0 * request_rate)

        该公式同时考虑历史请求量、实际冷启动缺失次数和当前请求速率。
        """
        return state.avg_cold_start * (
            0.6 * state.n_req
            + 1.5 * state.cold_miss_count
            + 2.0 * state.request_rate
        )

    def _resource_cost(self, state: FunctionState) -> float:
        """
        计算缓存资源代价。
        """
        return max(state.memory_units, 1) * self.config.resource_weight

    def _r_cache_raw(self, state: FunctionState, cache_utility: float) -> int:
        """
        计算缓存需求副本数 R_cache 的原始值。

        规则：
        - 正在执行请求时，至少保护 1 个副本；
        - 缓存效用高于阈值时，至少保留或预热 1 个 warm 副本；
        - 长时间空闲且没有请求时，R_cache 降为 0。
        """
        if state.in_flight_requests > 0:
            return 1

        if state.n_req == 0 and state.last_seen_age >= self.config.idle_age_threshold:
            return 0

        if cache_utility >= self.config.cache_utility_threshold:
            return 1

        return 0

    def _r_load_raw(self, state: FunctionState) -> int:
        """
        计算负载需求副本数 R_load。

        最小样例公式：

        R_load = ceil(request_rate / (replica_capacity_rps * target_utilization))
        """
        if state.request_rate <= 0:
            return 0

        effective_capacity = max(
            state.replica_capacity_rps * self.config.target_utilization,
            self.config.epsilon,
        )

        return int(math.ceil(state.request_rate / effective_capacity))

    def _clamp_replicas(self, replicas: int) -> int:
        """
        将副本数限制在配置上下界内。
        """
        return max(self.config.min_replicas, min(self.config.max_replicas, replicas))

    def _classify_action(
        self,
        state: FunctionState,
        r_cache: int,
        r_load: int,
        r_desired: int,
        cache_utility: float,
    ):
        """
        根据目标副本数与当前副本数生成动作和原因。
        """
        if r_desired > state.current_replicas:
            if r_load >= r_cache:
                return "scale_out", "load_requires_more_replicas"
            return "prewarm", "cache_requires_warm_replica"

        if r_desired < state.current_replicas:
            if state.in_flight_requests > 0:
                return "protect", "in_flight_request_protection"

            if r_cache == 0 and r_load == 0:
                return "scale_in", "no_cache_or_load_demand"

            return "scale_in", "desired_replicas_lower_than_current"

        if r_cache > 0 and state.current_replicas > 0:
            return "protect", "cache_or_load_keeps_replica"

        if cache_utility >= self.config.cache_utility_threshold and state.current_replicas == 0:
            return "prewarm", "cache_utility_high_but_budget_pending"

        return "observe", "no_replica_change"

    def _apply_cache_budget(self, decisions: List[AutoscalingDecision]) -> List[AutoscalingDecision]:
        """
        应用缓存容量预算。

        预算只约束由 R_cache 触发的 warm 副本保护或预热需求；
        由 R_load 触发的运行副本需求不被缓存预算削减。
        """
        cache_candidates = [
            item for item in decisions
            if item.r_cache > 0
        ]
        cache_candidates = sorted(cache_candidates, key=lambda item: item.cache_utility, reverse=True)

        used = 0
        selected = set()

        for item in cache_candidates:
            if used + item.memory_units <= self.config.cache_capacity_budget_units:
                used += item.memory_units
                selected.add(item.function_name)

        for item in decisions:
            load_demand = item.r_load > 0

            if item.r_cache > 0:
                if item.function_name in selected:
                    item.selected_by_cache_budget = True
                    item.capacity_status = "cache_selected_within_budget"
                else:
                    item.selected_by_cache_budget = False
                    item.capacity_status = "cache_budget_limited"

                    if not load_demand:
                        item.r_cache = 0
                        item.r_desired = max(item.r_cache, item.r_load)
                        item.delta = item.r_desired - item.current_replicas
                        item.action, item.reason = self._classify_action(
                            state_like(item),
                            item.r_cache,
                            item.r_load,
                            item.r_desired,
                            item.cache_utility,
                        )
            else:
                item.capacity_status = "no_cache_budget_required"
                item.selected_by_cache_budget = False

        return decisions

    @staticmethod
    def build_control_plans(decisions: List[AutoscalingDecision]) -> List[ControlPlan]:
        """
        将扩缩容决策转换为控制计划。
        """
        plans: List[ControlPlan] = []

        for decision in decisions:
            executor_required = decision.r_desired != decision.current_replicas
            safe_to_execute = True

            if decision.action == "scale_in" and decision.in_flight_requests > 0:
                safe_to_execute = False

            plans.append(
                ControlPlan(
                    time=decision.time,
                    function_name=decision.function_name,
                    current_replicas=decision.current_replicas,
                    target_replicas=decision.r_desired,
                    control_action=decision.action,
                    executor_required=executor_required,
                    safe_to_execute=safe_to_execute,
                    reason=decision.reason,
                )
            )

        return plans


def state_like(decision: AutoscalingDecision):
    """
    将 AutoscalingDecision 适配为 _classify_action 所需的最小状态对象。

    该函数只用于预算二次修正阶段，避免引入额外复杂数据结构。
    """
    class _State:
        pass

    state = _State()
    state.current_replicas = decision.current_replicas
    state.in_flight_requests = decision.in_flight_requests
    return state
