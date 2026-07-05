"""
文件作用：边缘缓存感知调度样例的数据结构定义。
"""

from dataclasses import dataclass


@dataclass
class NodeState:
    """
    边缘节点状态。

    字段：
    - node_name：节点名称；
    - edge_zone：节点所在边缘区域；
    - cpu_free：CPU 空闲比例；
    - memory_free：内存空闲比例；
    - current_load：当前负载比例；
    - network_latency_ms：从用户侧到节点的基础网络延迟；
    - supports_accel：是否支持加速能力。
    """

    node_name: str
    edge_zone: str
    cpu_free: float
    memory_free: float
    current_load: float
    network_latency_ms: float
    supports_accel: bool


@dataclass(frozen=True)
class FunctionProfile:
    """
    函数画像。

    字段：
    - cold_start_duration：函数冷启动额外耗时；
    - warm_duration：warm 路径执行耗时；
    - image_pull_duration：镜像未命中时的拉取耗时；
    - data_fetch_duration：数据未命中时的拉取耗时；
    - memory_demand：内存需求比例；
    - cpu_demand：CPU 需求比例；
    - preferred_zone：函数优先边缘区域；
    - require_accel：是否需要加速节点。
    """

    function_name: str
    cold_start_duration: float
    warm_duration: float
    image_pull_duration: float
    data_fetch_duration: float
    memory_demand: float
    cpu_demand: float
    preferred_zone: str
    require_accel: bool


@dataclass(frozen=True)
class CacheEntry:
    """
    缓存快照项。
    """

    cache_type: str
    cache_key: str
    node_name: str
    cached: bool
    freshness: float


@dataclass(frozen=True)
class RequestEvent:
    """
    请求事件。
    """

    request_id: int
    time: float
    function_name: str
    source_zone: str


@dataclass
class CandidateScore:
    """
    候选节点评分。
    """

    policy_name: str
    request_id: int
    time: float
    function_name: str
    candidate_node: str
    feasible: bool
    function_cache_hit: bool
    image_cache_hit: bool
    data_cache_hit: bool
    zone_match: bool
    accel_match: bool
    resource_score: float
    cache_score: float
    locality_score: float
    load_penalty: float
    latency_penalty: float
    total_score: float
    reason: str


@dataclass
class SchedulingResult:
    """
    请求级调度结果。
    """

    policy_name: str
    request_id: int
    time: float
    function_name: str
    source_zone: str
    selected_node: str
    function_cache_hit: bool
    image_cache_hit: bool
    data_cache_hit: bool
    estimated_latency: float
    cold_start_penalty: float
    image_pull_penalty: float
    data_fetch_penalty: float
    network_latency: float
    total_score: float
    reason: str
