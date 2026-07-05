"""
文件作用：函数实例缓存策略实现。

本文件实现三类缓存策略：
- FIFO：优先驱逐最早进入缓存的函数；
- LRU：优先驱逐最近最少访问的函数；
- UtilityAware：综合冷启动收益、访问频率和资源占用计算驱逐分数。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from cache_model import FunctionCache, EvictionEvent
from function_catalog import FunctionSpec
from workload import FunctionRequest


class CachePolicy(ABC):
    """
    缓存策略基类。
    """

    def __init__(self, name: str, capacity_units: int, catalog: Dict[str, FunctionSpec]):
        """
        初始化缓存策略。
        """
        self.name = name
        self.cache = FunctionCache(capacity_units)
        self.catalog = catalog

    def on_request(self, request: FunctionRequest) -> Tuple[bool, List[EvictionEvent]]:
        """
        处理一次请求，返回是否命中缓存以及驱逐事件列表。
        """
        function_name = request.function_name
        now = request.time
        spec = self.catalog[function_name]
        evictions: List[EvictionEvent] = []

        if self.cache.contains(function_name):
            self.cache.access(function_name, now)
            return True, evictions

        # 函数资源超过缓存容量时，不缓存该函数。
        if spec.memory_units > self.cache.capacity_units:
            return False, evictions

        while self.cache.used_units + spec.memory_units > self.cache.capacity_units:
            victim_name, score, reason = self.select_victim(request)
            victim = self.cache.remove(victim_name)
            evictions.append(
                EvictionEvent(
                    policy_name=self.name,
                    time=now,
                    function_name=function_name,
                    evicted_function=victim.function_name,
                    evicted_memory_units=victim.memory_units,
                    reason=reason,
                    score=score,
                    cache_used_after=self.cache.used_units,
                )
            )

        self.cache.add(spec, now)
        return False, evictions

    @abstractmethod
    def select_victim(self, request: FunctionRequest):
        """
        选择驱逐对象。
        """


class FIFOCachePolicy(CachePolicy):
    """
    FIFO 缓存策略。
    """

    def __init__(self, capacity_units: int, catalog: Dict[str, FunctionSpec]):
        super().__init__("fifo", capacity_units, catalog)

    def select_victim(self, request: FunctionRequest):
        """
        选择最早进入缓存的函数。
        """
        victim = min(self.cache.entries.values(), key=lambda item: item.inserted_time)
        return victim.function_name, victim.inserted_time, "oldest_inserted"


class LRUCachePolicy(CachePolicy):
    """
    LRU 缓存策略。
    """

    def __init__(self, capacity_units: int, catalog: Dict[str, FunctionSpec]):
        super().__init__("lru", capacity_units, catalog)

    def select_victim(self, request: FunctionRequest):
        """
        选择最近最少访问的函数。
        """
        victim = min(self.cache.entries.values(), key=lambda item: item.last_access_time)
        return victim.function_name, victim.last_access_time, "least_recently_used"


class UtilityAwareCachePolicy(CachePolicy):
    """
    冷启动收益感知缓存策略。

    策略思想：
    - 冷启动代价越高，越值得保留；
    - 近期访问次数越高，越值得保留；
    - 资源占用越大，保留代价越高；
    - 驱逐时选择效用最低的函数。

    效用定义：

    utility = cold_start_duration * (1 + access_count) / memory_units

    该公式是最小样例版本，后续可以替换为论文中的 R_cache 或更完整的在线效用模型。
    """

    def __init__(self, capacity_units: int, catalog: Dict[str, FunctionSpec]):
        super().__init__("utility_aware", capacity_units, catalog)

    def select_victim(self, request: FunctionRequest):
        """
        选择效用最低的函数。
        """
        victim = min(self.cache.entries.values(), key=self.entry_utility)
        return victim.function_name, self.entry_utility(victim), "lowest_utility"

    @staticmethod
    def entry_utility(entry) -> float:
        """
        计算缓存项效用。
        """
        return entry.cold_start_duration * (1.0 + entry.access_count) / max(entry.memory_units, 1)


def build_default_policies(capacity_units: int, catalog: Dict[str, FunctionSpec]):
    """
    构造默认策略列表。
    """
    return [
        FIFOCachePolicy(capacity_units, catalog),
        LRUCachePolicy(capacity_units, catalog),
        UtilityAwareCachePolicy(capacity_units, catalog),
    ]
