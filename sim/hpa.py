"""
Kubernetes HPA 风格自动伸缩器。

HorizontalPodAutoscaler 周期性读取函数副本的平均 CPU 利用率，并根据目标利用率计算期望副本数，通过 FaaS 系统执行扩容或缩容。
"""

import math

from sim.core import Environment
from sim.faas import FunctionState, FaasSystem
from sim.resource import MetricsServer


class HorizontalPodAutoscaler:

    
    

    """
    HPA 风格自动伸缩控制器。

    周期读取资源利用率，根据目标平均利用率计算期望副本数，并调用 FaaS 系统扩容或缩容。

    重要字段：
    - average_window: 计算平均资源利用率时向前回看的时间窗口。
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - reconcile_interval: 后台控制循环执行间隔。
    - target_tolerance: HPA 目标利用率容忍区间，用于减少抖动。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, env: Environment, average_window: int = 100, reconcile_interval: int = 15,
                 target_tolerance: float = 0.1):
        """
        初始化 HPA 控制器。

        average_window 表示计算平均 CPU 利用率的时间窗口，reconcile_interval 表示控制循环周期，target_tolerance 用于避免利用率在目标值附近频繁扩缩容。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - average_window: average_window 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：int。
        - reconcile_interval: 控制器重新计算决策的周期。 类型标注：int。
        - target_tolerance: target_tolerance 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.average_window = 100
        self.env = env
        self.reconcile_interval = reconcile_interval
        self.target_tolerance = target_tolerance

    def run(self):
        """
        周期性执行 HPA 扩缩容决策。

        控制器会遍历所有函数部署，读取 RUNNING 副本的平均 CPU 利用率，计算期望副本数，并在超过容忍区间时调用 faas.scale_up 或 faas.scale_down。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        while True:
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
                    yield from faas.scale_down(function_deployment.name, scale)
                else:
                    
                    scale = desired_replicas - len(running_replicas)
                    yield from faas.scale_up(function_deployment.name, scale)
