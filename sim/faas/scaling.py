"""
文件作用：函数自动伸缩后台进程实现，包含 scale-to-zero idler、基于请求数的扩缩容、平均 RPS 扩缩容和队列长度扩缩容逻辑。
主要类：FaasRequestScaler、AverageFaasRequestScaler、AverageQueueFaasRequestScaler。
主要函数：faas_idler。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import logging
import math

import numpy as np

from sim.core import Environment
from sim.faas import FaasSystem, FunctionState, FunctionDeployment

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


def faas_idler(env: Environment, inactivity_duration=300, reconcile_interval=30):
    """
    函数作用：周期检查空闲函数，在满足 idle 条件时缩容到 0。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；inactivity_duration：表示 inactivity、duration，在当前业务流程中作为输入参数、状态字段或计算结果使用。；reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    faas: FaasSystem = env.faas
    while True:
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
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
    类作用：FaasRequestScaler 类，封装 faas、request、scaler 相关状态和业务操作。
    核心方法：__init__、run、stop。
    """
    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：alert_window、env、fn、fn_name、function_invocations、reconcile_interval、running、threshold。
        参数：fn：函数定义对象或函数名。；env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.function_invocations：函数调用记录集合，用于统计调用次数和窗口内负载。
        self.function_invocations = dict()
        # 字段说明：self.reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。
        self.reconcile_interval = fn.scaling_config.rps_threshold_duration
        # 字段说明：self.threshold：判断阈值，用于带宽、利用率或调度谓词的条件判断。
        self.threshold = fn.scaling_config.rps_threshold
        # 字段说明：self.alert_window：伸缩判断使用的观测时间窗口。
        self.alert_window = fn.scaling_config.alert_window
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = True
        # 字段说明：self.fn_name：函数名称，用于按函数维度索引部署、副本、伸缩器和指标。
        self.fn_name = fn.name
        # 字段说明：self.fn：函数定义对象，保存函数名称、镜像集合和标签。
        self.fn = fn

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(self.reconcile_interval)
            if self.function_invocations.get(self.fn_name, None) is None:
                self.function_invocations[self.fn_name] = 0
            last_invocations = self.function_invocations.get(self.fn_name, 0)
            current_total_invocations = env.metrics.invocations.get(self.fn_name, 0)
            invocations = current_total_invocations - last_invocations
            self.function_invocations[self.fn_name] += invocations
            # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
            config = self.fn.scaling_config
            if (invocations / self.reconcile_interval) >= self.threshold:
                scale = (config.scale_factor / 100) * config.scale_max
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_up(self.fn_name, int(scale))
                logger.debug(f'scaled up {self.fn_name} by {scale}')
            else:
                scale = (config.scale_factor / 100) * config.scale_max
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_down(self.fn_name, int(scale))
                logger.debug(f'scaled down {self.fn_name} by {scale}')

    def stop(self):
        """
        函数作用：停止后台伸缩进程的循环。
        关键流程：
        - 写入对象字段：running。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = False


class AverageFaasRequestScaler:
    """
    类作用：AverageFaasRequestScaler 类，封装 average、faas、request、scaler 相关状态和业务操作。
    核心方法：__init__、run、stop。
    """

    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：alert_window、env、fn、fn_name、function_invocations、running、threshold。
        参数：fn：函数定义对象或函数名。；env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.function_invocations：函数调用记录集合，用于统计调用次数和窗口内负载。
        self.function_invocations = dict()
        # 字段说明：self.threshold：判断阈值，用于带宽、利用率或调度谓词的条件判断。
        self.threshold = fn.scaling_config.target_average_rps
        # 字段说明：self.alert_window：伸缩判断使用的观测时间窗口。
        self.alert_window = fn.scaling_config.alert_window
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = True
        # 字段说明：self.fn_name：函数名称，用于按函数维度索引部署、副本、伸缩器和指标。
        self.fn_name = fn.name
        # 字段说明：self.fn：函数定义对象，保存函数名称、镜像集合和标签。
        self.fn = fn

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
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
            average = invocations / running
            desired_replicas = math.ceil(running * (average / self.threshold))

            updated_desired_replicas = desired_replicas
            if len(conceived_replicas) > 0 or len(starting_replicas) > 0:
                if desired_replicas > len(running_replicas):
                    count = len(running_replicas) + len(conceived_replicas) + len(starting_replicas)
                    average = invocations / count
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
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_down(self.fn.name, scale)
            else:
                
                scale = desired_replicas - len(running_replicas)
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_up(self.fn.name, scale)

    def stop(self):
        """
        函数作用：停止后台伸缩进程的循环。
        关键流程：
        - 写入对象字段：running。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = False


class AverageQueueFaasRequestScaler:
    """
    类作用：AverageQueueFaasRequestScaler 类，封装 average、queue、faas、request、scaler 相关状态和业务操作。
    核心方法：__init__、run、stop。
    """

    def __init__(self, fn: FunctionDeployment, env: Environment):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：alert_window、env、fn、fn_name、running、threshold。
        参数：fn：函数定义对象或函数名。；env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.threshold：判断阈值，用于带宽、利用率或调度谓词的条件判断。
        self.threshold = fn.scaling_config.target_queue_length
        # 字段说明：self.alert_window：伸缩判断使用的观测时间窗口。
        self.alert_window = fn.scaling_config.alert_window
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = True
        # 字段说明：self.fn_name：函数名称，用于按函数维度索引部署、副本、伸缩器和指标。
        self.fn_name = fn.name
        # 字段说明：self.fn：函数定义对象，保存函数名称、镜像集合和标签。
        self.fn = fn

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        env: Environment = self.env
        faas: FaasSystem = env.faas
        while self.running:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
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
                in_queue.append(len(sim.queue.queue))
            if len(in_queue) == 0:
                average = 0
            else:
                average = int(math.ceil(np.median(np.array(in_queue))))

            desired_replicas = math.ceil(running * (average / self.threshold))

            updated_desired_replicas = desired_replicas
            if len(conceived_replicas) > 0 or len(starting_replicas) > 0:
                if desired_replicas > len(running_replicas):
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
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_down(self.fn.name, scale)
            else:
                
                scale = desired_replicas - len(running_replicas)
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from faas.scale_up(self.fn.name, scale)

    def stop(self):
        """
        函数作用：停止后台伸缩进程的循环。
        关键流程：
        - 写入对象字段：running。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.running：后台进程运行开关，控制伸缩器或监控器循环是否继续执行。
        self.running = False
