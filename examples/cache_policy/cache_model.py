"""
文件作用：函数实例缓存状态模型。

该文件定义缓存项、请求结果和驱逐事件等基础数据结构。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from function_catalog import FunctionSpec


@dataclass
class CacheEntry:
    """
    缓存项。

    字段：
    - function_name：函数名称；
    - memory_units：资源占用；
    - inserted_time：进入缓存时间；
    - last_access_time：最近访问时间；
    - access_count：访问次数；
    - cold_start_duration：冷启动代价，用于策略评分；
    """

    function_name: str
    memory_units: int
    inserted_time: float
    last_access_time: float
    access_count: int
    cold_start_duration: float


@dataclass
class RequestResult:
    """
    单次请求结果。
    """

    policy_name: str
    request_id: int
    time: float
    function_name: str
    cache_hit: bool
    latency: float
    cold_start_penalty: float
    cache_used_before: int
    cache_used_after: int
    cache_keys_after: str


@dataclass
class EvictionEvent:
    """
    驱逐事件。
    """

    policy_name: str
    time: float
    function_name: str
    evicted_function: str
    evicted_memory_units: int
    reason: str
    score: Optional[float]
    cache_used_after: int


@dataclass
class CacheStateRecord:
    """
    缓存状态记录。
    """

    policy_name: str
    time: float
    request_id: int
    function_name: str
    cache_used: int
    cache_capacity: int
    cache_keys: str


class FunctionCache:
    """
    函数实例缓存容器。

    该类只维护缓存状态，不决定驱逐对象。
    驱逐决策由具体 CachePolicy 实现。
    """

    def __init__(self, capacity_units: int):
        """
        初始化缓存。
        """
        self.capacity_units = capacity_units
        self.entries: Dict[str, CacheEntry] = {}

    @property
    def used_units(self) -> int:
        """
        返回当前缓存资源占用。
        """
        return sum(entry.memory_units for entry in self.entries.values())

    def contains(self, function_name: str) -> bool:
        """
        判断函数是否在缓存中。
        """
        return function_name in self.entries

    def access(self, function_name: str, now: float):
        """
        更新缓存项访问元信息。
        """
        entry = self.entries[function_name]
        entry.last_access_time = now
        entry.access_count += 1

    def add(self, spec: FunctionSpec, now: float):
        """
        添加函数实例到缓存。
        """
        self.entries[spec.function_name] = CacheEntry(
            function_name=spec.function_name,
            memory_units=spec.memory_units,
            inserted_time=now,
            last_access_time=now,
            access_count=1,
            cold_start_duration=spec.cold_start_duration,
        )

    def remove(self, function_name: str) -> CacheEntry:
        """
        删除缓存项。
        """
        return self.entries.pop(function_name)

    def keys_text(self) -> str:
        """
        返回缓存键集合的字符串形式。
        """
        return ";".join(sorted(self.entries.keys()))
