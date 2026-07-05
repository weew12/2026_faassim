"""
文件作用：冷启动感知缓存决策 Advisor。

该 Advisor 根据函数画像计算缓存效用，并生成 keep_warm、prewarm_candidate、
eviction_candidate 和 observe 四类决策。
"""

from typing import List

from decision_model import (
    CacheDecision,
    CacheDecisionConfig,
    ControlHint,
)
from profiles import FunctionProfile


class CacheDecisionAdvisor:
    """
    冷启动感知缓存决策器。

    评分思想：
    - 请求数越高，冷启动收益越高；
    - 冷启动越慢，收益越高；
    - 冷启动缺失次数越多，说明保持或预热的收益越明确；
    - 资源占用越高，缓存代价越高；
    - 正在执行的函数受保护，不进入驱逐。
    """

    def __init__(self, config: CacheDecisionConfig):
        """
        初始化 Advisor。
        """
        self.config = config

    def evaluate(self, profiles: List[FunctionProfile]) -> List[CacheDecision]:
        """
        计算所有函数的缓存决策，并根据容量预算标记是否入选。
        """
        raw_decisions = [self._evaluate_one(profile) for profile in profiles]
        return self._apply_capacity_budget(raw_decisions)

    def _evaluate_one(self, profile: FunctionProfile) -> CacheDecision:
        """
        计算单个函数的缓存决策。
        """
        cold_benefit = self._cold_benefit(profile)
        resource_cost = self._resource_cost(profile)
        utility_score = cold_benefit / max(resource_cost, self.config.epsilon)

        decision, reason = self._classify(profile, utility_score)
        priority = self._priority(profile, utility_score, decision)

        return CacheDecision(
            function_name=profile.function_name,
            current_replicas=profile.current_replicas,
            warm_replicas=profile.warm_replicas,
            memory_units=profile.memory_units,
            n_req=profile.n_req,
            cold_miss_count=profile.cold_miss_count,
            avg_cold_start=profile.avg_cold_start,
            request_rate=profile.request_rate,
            last_seen_age=profile.last_seen_age,
            in_flight_requests=profile.in_flight_requests,
            cold_benefit=cold_benefit,
            resource_cost=resource_cost,
            utility_score=utility_score,
            decision=decision,
            priority=priority,
            reason=reason,
            capacity_status="not_checked",
            selected_by_budget=False,
        )

    def _cold_benefit(self, profile: FunctionProfile) -> float:
        """
        计算冷启动收益。

        最小样例公式：

        cold_benefit = avg_cold_start * (0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate)

        该公式突出三个因素：
        - 历史请求量；
        - 实际冷启动缺失；
        - 当前请求速率。
        """
        return profile.avg_cold_start * (
            0.6 * profile.n_req
            + 1.4 * profile.cold_miss_count
            + 2.0 * profile.request_rate
        )

    def _resource_cost(self, profile: FunctionProfile) -> float:
        """
        计算资源代价。
        """
        return max(profile.memory_units, 1) * self.config.resource_weight

    def _classify(self, profile: FunctionProfile, utility_score: float):
        """
        将效用分数映射为缓存决策。
        """
        if profile.in_flight_requests > 0 and profile.current_replicas > 0:
            return "keep_warm", "in_flight_request_protection"

        if profile.current_replicas > 0:
            if (
                profile.n_req == 0
                and profile.in_flight_requests == 0
                and profile.last_seen_age >= self.config.idle_age_threshold
            ):
                return "eviction_candidate", "idle_warm_instance"

            if utility_score >= self.config.keep_warm_threshold:
                return "keep_warm", "high_cold_start_utility"

            if utility_score <= self.config.eviction_threshold:
                return "eviction_candidate", "low_cache_utility"

            return "observe", "warm_but_medium_utility"

        if utility_score >= self.config.prewarm_threshold:
            return "prewarm_candidate", "missing_but_high_utility"

        return "observe", "missing_but_low_utility"

    @staticmethod
    def _priority(profile: FunctionProfile, utility_score: float, decision: str) -> float:
        """
        计算决策优先级。
        """
        if decision == "eviction_candidate":
            return -utility_score

        if profile.in_flight_requests > 0:
            return utility_score + 1000.0

        return utility_score

    def _apply_capacity_budget(self, decisions: List[CacheDecision]) -> List[CacheDecision]:
        """
        根据容量预算选择 keep_warm 和 prewarm_candidate 对象。

        预算只用于标记 selected_by_budget，不改变原始 decision 字段。
        """
        candidates = [
            item for item in decisions
            if item.decision in {"keep_warm", "prewarm_candidate"}
        ]
        candidates = sorted(candidates, key=lambda item: item.priority, reverse=True)

        used = 0
        selected_names = set()

        for item in candidates:
            if used + item.memory_units <= self.config.capacity_budget_units:
                used += item.memory_units
                selected_names.add(item.function_name)

        for item in decisions:
            if item.decision in {"keep_warm", "prewarm_candidate"}:
                if item.function_name in selected_names:
                    item.capacity_status = "selected_within_budget"
                    item.selected_by_budget = True
                else:
                    item.capacity_status = "not_selected_budget_limited"
                    item.selected_by_budget = False
            elif item.decision == "eviction_candidate":
                item.capacity_status = "release_capacity_candidate"
                item.selected_by_budget = False
            else:
                item.capacity_status = "no_capacity_change"
                item.selected_by_budget = False

        return sorted(decisions, key=lambda item: item.priority, reverse=True)

    @staticmethod
    def build_control_hints(decisions: List[CacheDecision]) -> List[ControlHint]:
        """
        将缓存决策转换为控制建议。

        注意：
        本样例只生成控制建议，不执行真实扩缩容。
        """
        hints: List[ControlHint] = []

        for decision in decisions:
            if decision.decision == "keep_warm":
                hints.append(
                    ControlHint(
                        function_name=decision.function_name,
                        decision=decision.decision,
                        control_action="protect_current_replica",
                        target_replicas=max(decision.current_replicas, 1),
                        executor_required=False,
                        safe_to_execute=True,
                        reason=decision.reason,
                    )
                )
            elif decision.decision == "prewarm_candidate":
                hints.append(
                    ControlHint(
                        function_name=decision.function_name,
                        decision=decision.decision,
                        control_action="scale_to_one_if_selected",
                        target_replicas=1 if decision.selected_by_budget else 0,
                        executor_required=decision.selected_by_budget,
                        safe_to_execute=decision.selected_by_budget,
                        reason=decision.reason if decision.selected_by_budget else "budget_limited",
                    )
                )
            elif decision.decision == "eviction_candidate":
                hints.append(
                    ControlHint(
                        function_name=decision.function_name,
                        decision=decision.decision,
                        control_action="scale_to_zero_candidate",
                        target_replicas=0,
                        executor_required=True,
                        safe_to_execute=decision.in_flight_requests == 0,
                        reason=decision.reason,
                    )
                )
            else:
                hints.append(
                    ControlHint(
                        function_name=decision.function_name,
                        decision=decision.decision,
                        control_action="observe",
                        target_replicas=decision.current_replicas,
                        executor_required=False,
                        safe_to_execute=True,
                        reason=decision.reason,
                    )
                )

        return hints
