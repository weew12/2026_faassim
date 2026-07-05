"""
文件作用：缓存决策数据结构。

该文件定义缓存评分、缓存决策和控制建议的标准字段。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheDecisionConfig:
    """
    缓存决策配置。

    字段：
    - capacity_budget_units：实例缓存容量预算；
    - keep_warm_threshold：keep_warm 阈值；
    - prewarm_threshold：prewarm_candidate 阈值；
    - eviction_threshold：eviction_candidate 阈值；
    - idle_age_threshold：空闲时间阈值；
    - resource_weight：资源代价权重；
    - epsilon：分母保护项。
    """

    capacity_budget_units: int = 4
    keep_warm_threshold: float = 1.20
    prewarm_threshold: float = 1.00
    eviction_threshold: float = 0.35
    idle_age_threshold: float = 6.0
    resource_weight: float = 0.60
    epsilon: float = 1e-9


@dataclass
class CacheDecision:
    """
    单个函数的缓存决策结果。
    """

    function_name: str
    current_replicas: int
    warm_replicas: int
    memory_units: int
    n_req: int
    cold_miss_count: int
    avg_cold_start: float
    request_rate: float
    last_seen_age: float
    in_flight_requests: int
    cold_benefit: float
    resource_cost: float
    utility_score: float
    decision: str
    priority: float
    reason: str
    capacity_status: str
    selected_by_budget: bool


@dataclass
class ControlHint:
    """
    缓存决策对应的控制建议。

    字段：
    - control_action：控制动作；
    - target_replicas：目标副本数；
    - executor_required：是否需要执行器介入；
    - safe_to_execute：是否满足安全执行条件。
    """

    function_name: str
    decision: str
    control_action: str
    target_replicas: int
    executor_required: bool
    safe_to_execute: bool
    reason: str
