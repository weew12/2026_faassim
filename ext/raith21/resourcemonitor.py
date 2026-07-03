"""
文件作用：Raith21 专用资源监控进程，周期读取资源状态并写入资源窗口指标。
主要类：Raith21ResourceMonitor。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from typing import Dict, List

import numpy as np

from ext.raith21.functionsim import FunctionCall
from sim.core import Environment
from sim.faas import FaasSystem, FunctionState
from sim.oracle.oracle import ResourceOracle
from sim.resource import ResourceWindow


# 待办：这里保留了后续完善点，需要结合实验目标继续细化。

class Raith21ResourceMonitor:
    """
    类作用：Raith21 实验资源监控器，把资源状态按固定周期转为指标记录。
    核心方法：__init__、run。
    """

    def __init__(self, env: Environment, resource_oracle: ResourceOracle):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：env、metric_server、resource_oracle。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
        self.resource_oracle = resource_oracle
        # 字段说明：self.metric_server：资源指标服务器，缓存监控窗口并提供平均资源利用率查询。
        self.metric_server = env.metrics_server

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        faas: FaasSystem = self.env.faas
        while True:
            start_ts = self.env.now
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield self.env.timeout(1)
            end_ts = self.env.now
            # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
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
                        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
                        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
                        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
                        
                        sum = np.sum(trace_execution_durations)
                        
                        
                        cpu_usage = (sum * replica_usage['cpu'])
                        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
                        window = ResourceWindow(replica, min(1, cpu_usage))
                    self.metric_server.put(window)
