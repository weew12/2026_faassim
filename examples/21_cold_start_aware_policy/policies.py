"""
文件作用：冷启动感知保活策略实现。

本文件实现两个策略：
- FixedKeepAlivePolicy：固定保活窗口，作为基线；
- ColdStartAwarePolicy：根据冷启动代价、近期访问频率和资源占用动态计算保活窗口。
"""

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

from models import (
    EvictionEvent,
    FunctionProfile,
    PolicyDecision,
    RequestEvent,
    RequestResult,
    WarmEntry,
)


class KeepAlivePolicy(ABC):
    """
    函数实例保活策略基类。
    """

    def __init__(self, name: str, profiles: Dict[str, FunctionProfile], capacity_units: int):
        """
        初始化策略。
        """
        self.name = name
        self.profiles = profiles
        self.capacity_units = capacity_units
        self.entries: Dict[str, WarmEntry] = {}
        self.recent_access: Dict[str, Deque[float]] = defaultdict(deque)
        self.request_results: List[RequestResult] = []
        self.policy_decisions: List[PolicyDecision] = []
        self.evictions: List[EvictionEvent] = []

    @property
    def used_units(self) -> int:
        """
        返回当前 warm 实例容量占用。
        """
        return sum(entry.memory_units for entry in self.entries.values())

    def handle_request(self, request: RequestEvent):
        """
        处理一次请求，并记录策略结果。
        """
        self._expire_entries(request.time)

        profile = self.profiles[request.function_name]
        self._record_access(request.function_name, request.time)

        cache_hit = request.function_name in self.entries
        if cache_hit:
            latency = profile.warm_duration
            cold_start_penalty = 0.0
            decision_name = "extend_keep_alive"
            reason = "warm_hit"
        else:
            latency = profile.cold_start_duration + profile.warm_duration
            cold_start_penalty = profile.cold_start_duration
            decision_name = "keep_after_cold_start"
            reason = "cold_miss"

        keep_alive_window, utility = self.compute_keep_alive_window(request, profile, cache_hit)

        if cache_hit:
            entry = self.entries[request.function_name]
            entry.last_access_time = request.time
            entry.expire_time = request.time + keep_alive_window
            entry.access_count += 1
            entry.utility = utility
        else:
            self._ensure_capacity(profile, request.time)
            self.entries[request.function_name] = WarmEntry(
                function_name=request.function_name,
                memory_units=profile.memory_units,
                inserted_time=request.time,
                last_access_time=request.time,
                expire_time=request.time + keep_alive_window,
                access_count=1,
                utility=utility,
            )

        self.request_results.append(
            RequestResult(
                policy_name=self.name,
                request_id=request.request_id,
                time=request.time,
                function_name=request.function_name,
                cache_hit=cache_hit,
                latency=latency,
                cold_start_penalty=cold_start_penalty,
                keep_alive_window=keep_alive_window,
                cache_used_after=self.used_units,
                warm_keys_after=self._warm_keys_text(),
            )
        )

        self.policy_decisions.append(
            PolicyDecision(
                policy_name=self.name,
                time=request.time,
                request_id=request.request_id,
                function_name=request.function_name,
                decision=decision_name,
                reason=reason,
                utility=utility,
                keep_alive_window=keep_alive_window,
                expire_time=request.time + keep_alive_window,
                cache_used=self.used_units,
                cache_capacity=self.capacity_units,
                warm_keys=self._warm_keys_text(),
            )
        )

    def _expire_entries(self, now: float):
        """
        删除已经过期的 warm 实例。
        """
        expired_names = [
            name for name, entry in self.entries.items()
            if entry.expire_time <= now
        ]

        for name in expired_names:
            entry = self.entries.pop(name)
            self.evictions.append(
                EvictionEvent(
                    policy_name=self.name,
                    time=now,
                    function_name=name,
                    evicted_function=name,
                    reason="keep_alive_expired",
                    utility=entry.utility,
                    cache_used_after=self.used_units,
                )
            )

    def _ensure_capacity(self, profile: FunctionProfile, now: float):
        """
        确保加入新函数后不超过容量预算。
        """
        if profile.memory_units > self.capacity_units:
            return

        while self.used_units + profile.memory_units > self.capacity_units and self.entries:
            victim_name = self.select_victim()
            victim = self.entries.pop(victim_name)

            self.evictions.append(
                EvictionEvent(
                    policy_name=self.name,
                    time=now,
                    function_name=profile.function_name,
                    evicted_function=victim.function_name,
                    reason="capacity_pressure",
                    utility=victim.utility,
                    cache_used_after=self.used_units,
                )
            )

    def _record_access(self, function_name: str, now: float):
        """
        记录近期访问时间。
        """
        window = self.recent_access[function_name]
        window.append(now)

        while window and now - window[0] > 5.0:
            window.popleft()

    def recent_rate(self, function_name: str) -> float:
        """
        计算最近 5 个时间单位内的访问频率。
        """
        return len(self.recent_access[function_name]) / 5.0

    def _warm_keys_text(self) -> str:
        """
        返回当前 warm 函数集合。
        """
        return ";".join(sorted(self.entries.keys()))

    @abstractmethod
    def compute_keep_alive_window(
        self,
        request: RequestEvent,
        profile: FunctionProfile,
        cache_hit: bool,
    ) -> Tuple[float, float]:
        """
        计算保活窗口和效用。
        """

    @abstractmethod
    def select_victim(self) -> str:
        """
        选择容量压力下的驱逐对象。
        """


class FixedKeepAlivePolicy(KeepAlivePolicy):
    """
    固定 keep-alive 策略。
    """

    def __init__(self, profiles: Dict[str, FunctionProfile], capacity_units: int, fixed_window: float = 2.0):
        """
        初始化固定窗口策略。
        """
        super().__init__("fixed_keep_alive", profiles, capacity_units)
        self.fixed_window = fixed_window

    def compute_keep_alive_window(self, request, profile, cache_hit):
        """
        返回固定保活窗口。
        """
        utility = profile.cold_start_duration / max(profile.memory_units, 1)
        return self.fixed_window, utility

    def select_victim(self) -> str:
        """
        容量不足时驱逐最早过期的函数。
        """
        victim = min(self.entries.values(), key=lambda entry: entry.expire_time)
        return victim.function_name


class ColdStartAwarePolicy(KeepAlivePolicy):
    """
    冷启动感知 keep-alive 策略。

    策略思想：
    - 冷启动越慢，保活窗口越长；
    - 近期访问越频繁，保活窗口越长；
    - 资源占用越大，保活窗口越短；
    - 容量不足时驱逐效用最低的函数。
    """

    def __init__(
        self,
        profiles: Dict[str, FunctionProfile],
        capacity_units: int,
        base_window: float = 0.8,
        max_window: float = 6.0,
    ):
        """
        初始化冷启动感知策略。
        """
        super().__init__("cold_start_aware", profiles, capacity_units)
        self.base_window = base_window
        self.max_window = max_window

    def compute_keep_alive_window(self, request, profile, cache_hit):
        """
        动态计算保活窗口和效用。

        最小样例公式：

        utility = cold_start_duration * (1 + recent_rate) / memory_units

        keep_alive_window = base_window + 1.2 * cold_start_duration + 2.0 * recent_rate - 0.3 * memory_units
        """
        rate = self.recent_rate(profile.function_name)
        utility = profile.cold_start_duration * (1.0 + rate) / max(profile.memory_units, 1)

        window = (
            self.base_window
            + 1.2 * profile.cold_start_duration
            + 2.0 * rate
            - 0.3 * profile.memory_units
        )
        window = max(0.5, min(self.max_window, window))

        return window, utility

    def select_victim(self) -> str:
        """
        容量不足时驱逐效用最低的函数；效用相同则驱逐最久未访问的函数。
        """
        victim = min(
            self.entries.values(),
            key=lambda entry: (entry.utility, entry.last_access_time),
        )
        return victim.function_name


def build_default_policies(profiles: Dict[str, FunctionProfile], capacity_units: int):
    """
    构造默认策略列表。
    """
    return [
        FixedKeepAlivePolicy(profiles, capacity_units),
        ColdStartAwarePolicy(profiles, capacity_units),
    ]
