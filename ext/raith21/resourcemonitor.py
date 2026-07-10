"""
Raith21 节点资源监控进程。

本模块在通用 ResourceMonitor 基础上周期聚合节点资源占用，并写入节点级资源利用率指标。
"""

from typing import Dict, List

import numpy as np

from ext.raith21.functionsim import FunctionCall
from sim.core import Environment
from sim.faas import FaasSystem, FunctionState
from sim.oracle.oracle import ResourceOracle
from sim.resource import ResourceWindow



class Raith21ResourceMonitor:
    """
    Raith21 节点资源监控器。

    周期汇总 NodeResourceUtilization.total_utilization，并记录节点级 CPU、内存及扩展资源指标。

    关键字段:
        env: faas-sim 仿真环境。
        resource_oracle: 资源画像 Oracle。
        metric_server: 资源采样窗口服务。
    """

    def __init__(self, env: Environment, resource_oracle: ResourceOracle):
        """
        初始化 Raith21ResourceMonitor。

        建立字段：env、resource_oracle、metric_server。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.env = env
        self.resource_oracle = resource_oracle
        self.metric_server = env.metrics_server

    def run(self):
        """
        每个仿真时间单位计算各运行副本的 CPU 时间占比。

        方法先按节点缓存当前窗口内的调用区间，再计算每个副本与窗口重叠的执行时长，
        乘以资源画像中的 CPU 系数后写入 MetricsServer。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        faas: FaasSystem = self.env.faas
        while True:
            start_ts = self.env.now
            yield self.env.timeout(1)
            end_ts = self.env.now
            # 同一节点上的副本共享调用历史；每个窗口只查询一次，避免重复扫描 NodeState。
            call_cache: Dict[str, List[FunctionCall]] = {}
            for function_deployment in faas.get_deployments():
                for replica in faas.get_replicas(function_deployment.name, FunctionState.RUNNING):
                    node_name = replica.node.name
                    calls = call_cache.get(node_name, None)
                    if calls is None:
                        calls = replica.node.get_calls_in_timeframe(start_ts, end_ts)
                        call_cache[node_name] = calls
                    trace_execution_durations = []
                    replica_usage = self.resource_oracle.get_resources(node_name, replica.function.image)
                    for call in calls:
                        if call.replica.pod.name == replica.pod.name:
                            # 只统计调用区间与 [start_ts, end_ts] 的交集。
                            last_start = start_ts if start_ts >= call.start else call.start

                            if call.end is not None:
                                first_end = end_ts if end_ts <= call.end else call.end
                            else:
                                first_end = end_ts

                            overlap = first_end - last_start
                            trace_execution_durations.append(overlap)
                    if len(calls) == 0:
                        window = ResourceWindow(replica, 0)
                    else:
                        # 窗口内执行秒数乘以 CPU 画像，结果截断到 1，表示单副本 CPU 利用率。
                        sum = np.sum(trace_execution_durations)
                        cpu_usage = (sum * replica_usage['cpu'])
                        window = ResourceWindow(replica, min(1, cpu_usage))
                    self.metric_server.put(window)
