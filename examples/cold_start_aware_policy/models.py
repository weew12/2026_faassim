"""
文件作用：冷启动感知策略样例的数据结构定义。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FunctionProfile:
    """
    函数画像。

    字段：
    - function_name：函数名称；
    - cold_start_duration：冷启动额外耗时；
    - warm_duration：热路径执行耗时；
    - memory_units：warm 实例占用的抽象缓存容量。
    """

    function_name: str
    cold_start_duration: float
    warm_duration: float
    memory_units: int


@dataclass(frozen=True)
class RequestEvent:
    """
    请求事件。
    """

    request_id: int
    time: float
    function_name: str


@dataclass
class WarmEntry:
    """
    warm 实例缓存项。

    字段：
    - function_name：函数名称；
    - memory_units：容量占用；
    - inserted_time：进入 warm 缓存的时间；
    - last_access_time：最近访问时间；
    - expire_time：计划过期时间；
    - access_count：访问次数；
    - utility：最近一次计算得到的保活效用。
    """

    function_name: str
    memory_units: int
    inserted_time: float
    last_access_time: float
    expire_time: float
    access_count: int
    utility: float


@dataclass
class RequestResult:
    """
    请求级结果。
    """

    policy_name: str
    request_id: int
    time: float
    function_name: str
    cache_hit: bool
    latency: float
    cold_start_penalty: float
    keep_alive_window: float
    cache_used_after: int
    warm_keys_after: str


@dataclass
class PolicyDecision:
    """
    策略决策记录。
    """

    policy_name: str
    time: float
    request_id: int
    function_name: str
    decision: str
    reason: str
    utility: float
    keep_alive_window: float
    expire_time: float
    cache_used: int
    cache_capacity: int
    warm_keys: str


@dataclass
class EvictionEvent:
    """
    驱逐或过期事件。
    """

    policy_name: str
    time: float
    function_name: str
    evicted_function: str
    reason: str
    utility: Optional[float]
    cache_used_after: int
