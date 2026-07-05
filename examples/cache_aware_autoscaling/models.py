"""
文件作用：缓存状态感知扩缩容的数据结构定义。

本样例不直接调用 faas-sim 的扩缩容执行器，而是先把 R_cache、R_load 和 R_desired
的计算过程独立抽象出来，便于理解缓存状态如何进入扩缩容决策。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionState:
    """
    单个时间点上的函数状态。

    字段：
    - time：仿真时间或采样轮次；
    - function_name：函数名称；
    - current_replicas：当前副本数；
    - warm_replicas：当前 warm 副本数；
    - n_req：观察窗口内请求数；
    - request_rate：请求速率；
    - avg_response_time：平均热路径响应时间；
    - avg_cold_start：平均冷启动耗时；
    - cold_miss_count：观察窗口内冷启动缺失次数；
    - memory_units：单个 warm 实例占用的缓存容量单位；
    - replica_capacity_rps：单副本可承载请求速率；
    - in_flight_requests：正在执行的请求数；
    - last_seen_age：距离最近一次请求的时间。
    """

    time: float
    function_name: str
    current_replicas: int
    warm_replicas: int
    n_req: int
    request_rate: float
    avg_response_time: float
    avg_cold_start: float
    cold_miss_count: int
    memory_units: int
    replica_capacity_rps: float
    in_flight_requests: int
    last_seen_age: float


@dataclass(frozen=True)
class AutoscalingConfig:
    """
    缓存状态感知扩缩容配置。

    字段：
    - target_utilization：目标单副本利用率；
    - cache_utility_threshold：缓存保护阈值；
    - idle_age_threshold：空闲释放阈值；
    - cache_capacity_budget_units：总缓存容量预算；
    - min_replicas：最小副本数；
    - max_replicas：最大副本数；
    - resource_weight：资源代价权重；
    - epsilon：分母保护项。
    """

    target_utilization: float = 0.70
    cache_utility_threshold: float = 1.00
    idle_age_threshold: float = 6.0
    cache_capacity_budget_units: int = 5
    min_replicas: int = 0
    max_replicas: int = 5
    resource_weight: float = 0.60
    epsilon: float = 1e-9


@dataclass
class AutoscalingDecision:
    """
    单个函数在单个时间点上的扩缩容决策。
    """

    time: float
    function_name: str
    current_replicas: int
    warm_replicas: int
    request_rate: float
    n_req: int
    avg_cold_start: float
    memory_units: int
    in_flight_requests: int
    last_seen_age: float
    cold_benefit: float
    resource_cost: float
    cache_utility: float
    r_cache_raw: int
    r_cache: int
    r_load_raw: int
    r_load: int
    r_desired_before_budget: int
    r_desired: int
    delta: int
    action: str
    reason: str
    selected_by_cache_budget: bool
    capacity_status: str


@dataclass
class ControlPlan:
    """
    扩缩容控制计划。

    字段：
    - control_action：动作类型；
    - target_replicas：目标副本数；
    - executor_required：是否需要执行器介入；
    - safe_to_execute：是否满足安全执行条件。
    """

    time: float
    function_name: str
    current_replicas: int
    target_replicas: int
    control_action: str
    executor_required: bool
    safe_to_execute: bool
    reason: str
