"""
文件作用：负载均衡器样例使用的可观测轮询负载均衡器。

faas-sim 默认负载均衡器是 RoundRobinLoadBalancer。
本样例实现 InstrumentedRoundRobinLoadBalancer，保持轮询选择语义，
同时把每次请求路由决策写入 load_balancer 指标，便于实验后分析。
"""

import logging
from collections import defaultdict

from sim.faas import LoadBalancer, FunctionRequest, FunctionReplica

logger = logging.getLogger(__name__)


class InstrumentedRoundRobinLoadBalancer(LoadBalancer):
    """
    可观测轮询负载均衡器。

    业务职责：
    - 读取指定函数当前 RUNNING 状态副本；
    - 按函数维度维护轮询计数器；
    - 将请求依次分配给不同副本；
    - 把每次路由决策记录到 metrics 的 load_balancer 表中。

    说明：
    该类不改变 faas-sim 默认轮询负载均衡语义，只额外记录路由事件。
    因此它适合用于理解原生负载均衡行为。
    """

    policy_name = "instrumented_round_robin"

    def __init__(self, env, replicas) -> None:
        """
        初始化负载均衡器。

        参数：
        - env：faas-sim 运行环境；
        - replicas：FaaS 系统维护的函数副本索引。
        """
        super().__init__(env, replicas)
        self.counters = defaultdict(lambda: 0)

    def next_replica(self, request: FunctionRequest) -> FunctionReplica:
        """
        为一次函数请求选择目标副本。

        参数：
        - request：函数调用请求。

        返回：
        - FunctionReplica：被选中的运行副本。

        业务流程：
        1. 读取目标函数的所有 RUNNING 副本；
        2. 根据函数名读取轮询计数器；
        3. 按 index = counter % running_replicas 选择副本；
        4. 更新计数器；
        5. 记录 load_balancer 指标；
        6. 返回被选中的副本。
        """
        running_replicas = self.get_running_replicas(request.name)

        if not running_replicas:
            raise RuntimeError(f"function {request.name} has no running replicas")

        index = self.counters[request.name] % len(running_replicas)
        self.counters[request.name] = (index + 1) % len(running_replicas)

        replica = running_replicas[index]

        logger.info(
            "[simtime=%.2f] route request=%s function=%s to replica_id=%s node=%s index=%d/%d",
            self.env.now,
            request.request_id,
            request.name,
            id(replica),
            replica.node.name,
            index,
            len(running_replicas),
        )

        # 记录负载均衡决策。后续 analysis.py 会导出 load_balancer.csv。
        # simtime 字段塞到 value 字典里，extract_dataframe 后会作为 "simtime" 列存在，
        # 便于按 (function_name, replica_id, simtime) 做 probe×invocation join。
        self.env.metrics.log(
            "load_balancer",
            {
                "request_id": request.request_id,
                "replica_index": index,
                "running_replicas": len(running_replicas),
                "simtime": float(self.env.now),
            },
            function_name=request.name,
            selected_node=replica.node.name,
            selected_image=replica.image,
            selected_replica_id=id(replica),
            policy=self.policy_name,
        )

        return replica
