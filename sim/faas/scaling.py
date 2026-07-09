"""
FaaS 自动伸缩策略。

本模块实现基于请求数量、平均请求速率、每副本队列长度等指标的伸缩器。伸缩器通常作为后台 SimPy 进程周期性运行。

阅读建议：对比三个 scaler 的指标来源：请求计数、平均 RPS、队列长度。
"""

import logging
import math

import numpy as np

from sim.core import Environment
from sim.faas import FaasSystem, FunctionState, FunctionDeployment

logger = logging.getLogger(__name__)


def faas_idler(env: Environment, inactivity_duration=300, reconcile_interval=30):
    """
    scale-to-zero 空闲检测后台进程。

    周期检查允许 scale_zero 的函数；若运行副本存在且距离上次调用超过 inactivity_duration，则触发 suspend。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - inactivity_duration: 判定函数空闲的持续时间阈值。
    - reconcile_interval: 控制器重新计算决策的周期。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    faas: FaasSystem = env.faas
    while True:
        yield env.timeout(reconcile_interval)

        for deployment in faas.get_deployments():
            if not deployment.scaling_config.scale_zero:
                continue

            name = deployment.name
            if len(faas.get_replicas(name, FunctionState.RUNNING)) == 0:
                continue

            idle_time = env.now - env.metrics.last_invocation[name]
            if idle_time >= inactivity_duration:
                env.process(faas.suspend(name))
                logger.debug('%.2f function %s has been idle for %.2fs', env.now, name, idle_time)


class FaasRequestScaler:

    """
    基于请求数量的自动伸缩器。

    周期检查请求计数是否超过阈值，并根据伸缩配置调整副本数。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - function_invocations: 上一次观察窗口中的函数调用计数缓存。
    - reconcile_interval: 后台控制循环执行间隔。
    - threshold: 伸缩阈值，超过或低于该值会触发扩缩容判断。
    - alert_window: 伸缩观察窗口长度。
    - running: 后台伸缩器是否继续运行的开关。
    - fn_name: 当前伸缩器或副本对应的函数名。
    - fn: 函数定义或函数部署对象，表示当前操作针对的业务函数。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        初始化 FaasRequestScaler 对象。

        主要建立字段：env、function_invocations、reconcile_interval、threshold、alert_window、running、fn_name、fn。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env
        self.function_invocations = dict()
        self.reconcile_interval = fn.scaling_config.rps_threshold_duration
        self.threshold = fn.scaling_config.rps_threshold
        self.alert_window = fn.scaling_config.alert_window
        self.running = True
        self.fn_name = fn.name
        self.fn = fn

    def run(self):
        """
        按固定周期根据最近请求速率扩缩容。

        如果窗口内 RPS 超过阈值则扩容，否则缩容；扩缩容幅度由 scale_factor 和 scale_max 共同决定。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            yield env.timeout(self.reconcile_interval)
            if self.function_invocations.get(self.fn_name, None) is None:
                self.function_invocations[self.fn_name] = 0
            # 通过“当前累计调用数 - 上次累计调用数”得到本观察周期内新增请求量。
            last_invocations = self.function_invocations.get(self.fn_name, 0)
            current_total_invocations = env.metrics.invocations.get(self.fn_name, 0)
            invocations = current_total_invocations - last_invocations
            self.function_invocations[self.fn_name] += invocations
            config = self.fn.scaling_config
            # 这里把窗口内请求量除以周期长度近似为 RPS，再与阈值比较。
            if (invocations / self.reconcile_interval) >= self.threshold:
                scale = (config.scale_factor / 100) * config.scale_max
                yield from faas.scale_up(self.fn_name, int(scale))
                logger.debug(f'scaled up {self.fn_name} by {scale}')
            else:
                scale = (config.scale_factor / 100) * config.scale_max
                yield from faas.scale_down(self.fn_name, int(scale))
                logger.debug(f'scaled down {self.fn_name} by {scale}')

    def stop(self):
        """
        停止请求数量伸缩器。

        将 running 置为 False 后，run 循环会在下一次条件检查时退出。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.running = False


class AverageFaasRequestScaler:
    """
    基于平均 RPS 的自动伸缩器。

    按窗口统计每副本请求速率，并向目标平均 RPS 靠拢。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - function_invocations: 上一次观察窗口中的函数调用计数缓存。
    - threshold: 伸缩阈值，超过或低于该值会触发扩缩容判断。
    - alert_window: 伸缩观察窗口长度。
    - running: 后台伸缩器是否继续运行的开关。
    - fn_name: 当前伸缩器或副本对应的函数名。
    - fn: 函数定义或函数部署对象，表示当前操作针对的业务函数。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        初始化 AverageFaasRequestScaler 对象。

        主要建立字段：env、function_invocations、threshold、alert_window、running、fn_name、fn。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env
        self.function_invocations = dict()
        self.threshold = fn.scaling_config.target_average_rps
        self.alert_window = fn.scaling_config.alert_window
        self.running = True
        self.fn_name = fn.name
        self.fn = fn

    def run(self):
        """
        按平均每副本请求数调整副本数量。

        方法计算窗口内新增请求与运行副本数的比值，推导期望副本数，并用阈值带避免频繁抖动。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            yield env.timeout(self.alert_window)
            if self.function_invocations.get(self.fn_name, None) is None:
                self.function_invocations[self.fn_name] = 0
            running_replicas = faas.get_replicas(self.fn.name, FunctionState.RUNNING)
            running = len(running_replicas)
            if running == 0:
                continue

            conceived_replicas = faas.get_replicas(self.fn.name, FunctionState.CONCEIVED)
            starting_replicas = faas.get_replicas(self.fn.name, FunctionState.STARTING)

            last_invocations = self.function_invocations.get(self.fn_name, 0)
            current_total_invocations = env.metrics.invocations.get(self.fn_name, 0)
            invocations = current_total_invocations - last_invocations
            self.function_invocations[self.fn_name] += invocations
            # average 表示本窗口中平均每个运行副本承担了多少请求。
            # desired_replicas 按 Kubernetes HPA 类似公式 current * current_metric / target_metric 推导。
            average = invocations / running
            desired_replicas = math.ceil(running * (average / self.threshold))

            updated_desired_replicas = desired_replicas
            if len(conceived_replicas) > 0 or len(starting_replicas) > 0:
                if desired_replicas > len(running_replicas):
                    # 已经有副本在创建或启动中时，把这些副本也纳入预估，避免重复过度扩容。
                    count = len(running_replicas) + len(conceived_replicas) + len(starting_replicas)
                    average = invocations / count
                    updated_desired_replicas = math.ceil(running * (average / self.threshold))

            if desired_replicas > len(running_replicas) and updated_desired_replicas < len(running_replicas):
                
                continue

            # 目标附近的微小波动不触发扩缩容，减少副本数量来回抖动。
            ratio = average / self.threshold
            if 1 > ratio >= 1 - self.fn.scaling_config.target_average_rps_threshold:
                
                continue

            if 1 < ratio < 1 + self.fn.scaling_config.target_average_rps_threshold:
                continue

            if desired_replicas < len(running_replicas):
                
                scale = len(running_replicas) - desired_replicas
                yield from faas.scale_down(self.fn.name, scale)
            else:
                
                scale = desired_replicas - len(running_replicas)
                yield from faas.scale_up(self.fn.name, scale)

    def stop(self):
        """
        停止平均 RPS 伸缩器。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.running = False


class AverageQueueFaasRequestScaler:
    """
    基于队列长度的自动伸缩器。

    根据每副本平均队列长度决定是否扩容或缩容。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - threshold: 伸缩阈值，超过或低于该值会触发扩缩容判断。
    - alert_window: 伸缩观察窗口长度。
    - running: 后台伸缩器是否继续运行的开关。
    - fn_name: 当前伸缩器或副本对应的函数名。
    - fn: 函数定义或函数部署对象，表示当前操作针对的业务函数。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        初始化 AverageQueueFaasRequestScaler 对象。

        主要建立字段：env、threshold、alert_window、running、fn_name、fn。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env
        self.threshold = fn.scaling_config.target_queue_length
        self.alert_window = fn.scaling_config.alert_window
        self.running = True
        self.fn_name = fn.name
        self.fn = fn

    def run(self):
        """
        按副本队列长度调整副本数量。

        方法读取每个运行副本模拟器中的队列长度，用中位数代表当前压力，并据此计算期望副本数。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            yield env.timeout(self.alert_window)
            running_replicas = faas.get_replicas(self.fn.name, FunctionState.RUNNING)
            running = len(running_replicas)
            if running == 0:
                continue

            conceived_replicas = faas.get_replicas(self.fn.name, FunctionState.CONCEIVED)
            starting_replicas = faas.get_replicas(self.fn.name, FunctionState.STARTING)

            in_queue = []
            for replica in running_replicas:
                sim: 'InterferenceAwarePythonHttpSimulator' = replica.simulator
                # 队列长度来自具体 simulator 的 simpy.Resource 队列。
                # 这要求使用该 scaler 的模拟器提供 queue 字段。
                in_queue.append(len(sim.queue.queue))
            if len(in_queue) == 0:
                average = 0
            else:
                # 使用中位数而不是平均值，避免少数异常长队列对整体决策影响过大。
                average = int(math.ceil(np.median(np.array(in_queue))))

            desired_replicas = math.ceil(running * (average / self.threshold))

            updated_desired_replicas = desired_replicas
            if len(conceived_replicas) > 0 or len(starting_replicas) > 0:
                if desired_replicas > len(running_replicas):
                    # 对正在创建/启动的副本临时补 0 队列，表示它们很快会分担压力。
                    for i in range(len(conceived_replicas) + len(starting_replicas)):
                        in_queue.append(0)

                    average = int(math.ceil(np.median(np.array(in_queue))))
                    updated_desired_replicas = math.ceil(running * (average / self.threshold))

            if desired_replicas > len(running_replicas) and updated_desired_replicas < len(running_replicas):
                
                continue

            ratio = average / self.threshold
            if 1 > ratio >= 1 - self.fn.scaling_config.target_average_rps_threshold:
                
                continue

            if 1 < ratio < 1 + self.fn.scaling_config.target_average_rps_threshold:
                continue

            if desired_replicas < len(running_replicas):
                
                scale = len(running_replicas) - desired_replicas
                yield from faas.scale_down(self.fn.name, scale)
            else:
                
                scale = desired_replicas - len(running_replicas)
                yield from faas.scale_up(self.fn.name, scale)

    def stop(self):
        """
        停止队列长度伸缩器。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.running = False
