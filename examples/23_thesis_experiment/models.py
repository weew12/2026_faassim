"""
文件作用：论文实验样例的数据结构定义。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FunctionProfile:
    """
    函数画像。
    """

    function_name: str
    cold_start_duration: float
    warm_duration: float
    image_pull_duration: float
    data_fetch_duration: float
    memory_units: int
    replica_capacity_rps: float
    cpu_demand: float
    memory_demand: float
    preferred_zone: str
    require_accel: bool


@dataclass
class NodeState:
    """
    节点状态。
    """

    node_name: str
    edge_zone: str
    cpu_free: float
    memory_free: float
    current_load: float
    network_latency_ms: float
    supports_accel: bool


@dataclass(frozen=True)
class WorkloadEvent:
    """
    请求事件。
    """

    request_id: int
    time: float
    function_name: str
    source_zone: str
    phase: str


@dataclass(frozen=True)
class ExperimentCase:
    """
    实验 case 配置。
    """

    case_id: str
    policy_name: str
    use_cache_decision: bool
    use_load_scaling: bool
    use_cache_aware_scheduler: bool
    cache_capacity_units: int
    target_utilization: float
    cache_utility_threshold: float
    base_keep_alive: float
    max_keep_alive: float
    description: str


@dataclass
class WarmEntry:
    """
    函数 warm 实例缓存项。
    """

    function_name: str
    node_name: str
    memory_units: int
    expire_time: float
    last_access_time: float
    access_count: int
    utility: float


@dataclass
class RequestResult:
    """
    请求级实验结果。
    """

    case_id: str
    policy_name: str
    request_id: int
    time: float
    phase: str
    function_name: str
    source_zone: str
    selected_node: str
    warm_hit: bool
    image_cache_hit: bool
    data_cache_hit: bool
    latency: float
    warm_duration: float
    cold_start_penalty: float
    image_pull_penalty: float
    data_fetch_penalty: float
    network_latency: float
    r_cache: int
    r_load: int
    r_desired: int
    cache_utility: float
    cache_used_after: int
    warm_keys_after: str


@dataclass
class ControlDecision:
    """
    R_cache / R_load 控制决策日志。
    """

    case_id: str
    policy_name: str
    request_id: int
    time: float
    function_name: str
    recent_rate: float
    cold_benefit: float
    resource_cost: float
    cache_utility: float
    r_cache: int
    r_load: int
    r_desired: int
    current_replicas: int
    action: str
    reason: str


@dataclass
class CandidateScore:
    """
    候选节点评分。
    """

    case_id: str
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
    selected: bool
    reason: str


@dataclass
class EvictionEvent:
    """
    函数缓存驱逐或过期事件。
    """

    case_id: str
    policy_name: str
    time: float
    function_name: str
    evicted_function: str
    evicted_node: str
    reason: str
    utility: Optional[float]
    cache_used_after: int
