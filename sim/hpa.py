"""
文件作用：Kubernetes HPA 风格自动伸缩器，周期读取平均 CPU 利用率并根据目标利用率调整函数副本数。
主要类：HorizontalPodAutoscaler。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import math

from sim.core import Environment
from sim.faas import FunctionState, FaasSystem
from sim.resource import MetricsServer


class HorizontalPodAutoscaler:

    
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。

    """
    类作用：HPA 风格伸缩器，按平均 CPU 利用率周期性调整函数副本数。
    核心方法：__init__、run。
    """
    def __init__(self, env: Environment, average_window: int = 100, reconcile_interval: int = 15,
                 target_tolerance: float = 0.1):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：average_window、env、reconcile_interval、target_tolerance。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；average_window：平均值计算窗口，用于 HPA 或资源指标聚合。；reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。；target_tolerance：目标容忍范围，用于避免伸缩器在目标附近频繁抖动。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.average_window：平均值计算窗口，用于 HPA 或资源指标聚合。
        self.average_window = 100
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。
        self.reconcile_interval = reconcile_interval
        # 字段说明：self.target_tolerance：目标容忍范围，用于避免伸缩器在目标附近频繁抖动。
        self.target_tolerance = target_tolerance

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        while True:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield self.env.timeout(self.reconcile_interval)
            metrics_server: MetricsServer = self.env.metrics_server
            faas: FaasSystem = self.env.faas
            for function_deployment in faas.get_deployments():
                running_replicas = faas.get_replicas(function_deployment.name, FunctionState.RUNNING)
                if len(running_replicas) == 0:
                    continue
                conceived_replicas = faas.get_replicas(function_deployment.name, FunctionState.CONCEIVED)
                starting_replicas = faas.get_replicas(function_deployment.name, FunctionState.STARTING)
                sum_cpu = 0

                for replica in running_replicas:
                    sum_cpu += metrics_server.get_average_cpu_utilization(replica, self.average_window)

                average_cpu = sum_cpu / len(running_replicas)

                target_avg_utilization = function_deployment.scaling_config.target_average_utilization
                desired_replicas = math.ceil(
                    len(running_replicas) * (average_cpu / target_avg_utilization))

                updated_desired_replicas = desired_replicas
                if len(conceived_replicas) > 0 or len(starting_replicas) > 0:
                    if desired_replicas > len(running_replicas):
                        count = len(running_replicas) + len(conceived_replicas) + len(starting_replicas)
                        average_cpu = sum_cpu / count
                        updated_desired_replicas = math.ceil(
                            len(running_replicas) * (average_cpu / target_avg_utilization))

                if desired_replicas > len(running_replicas) and updated_desired_replicas < len(running_replicas):
                    
                    continue

                ratio = average_cpu / target_avg_utilization
                if 1 > ratio >= 1 - self.target_tolerance:
                    
                    continue

                if 1 < ratio < 1 + self.target_tolerance:
                    continue

                if desired_replicas < len(running_replicas):
                    
                    scale = len(running_replicas) - desired_replicas
                    # 仿真推进：向 SimPy 事件队列交出控制权。
                    yield from faas.scale_down(function_deployment.name, scale)
                else:
                    
                    scale = desired_replicas - len(running_replicas)
                    # 仿真推进：向 SimPy 事件队列交出控制权。
                    yield from faas.scale_up(function_deployment.name, scale)
