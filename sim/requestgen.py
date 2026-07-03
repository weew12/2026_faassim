"""
文件作用：请求到达模型和工作负载生成器，提供固定、正弦、随机游走、指数分布和预录制到达间隔等请求模式。
主要函数：constant_rps_profile、sine_rps_profile、randomwalk_rps_profile、static_arrival_profile、expovariate_arrival_profile、pre_recorded_profile、function_trigger、run_arrival_profile、save_requests。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import logging
import math
import pickle
import random
import time

import numpy as np
import pandas as pd
import simpy

from sim.core import Environment
from sim.faas import FunctionRequest, FunctionDeployment

# 字段说明：__all__：模块导出符号列表，控制 from package import * 时暴露哪些对象。
__all__ = [
    'constant_rps_profile',
    'sine_rps_profile',
    'randomwalk_rps_profile',
    'static_arrival_profile',
    'expovariate_arrival_profile',
    'function_trigger',
    'run_arrival_profile',
    'save_requests',
    'pre_recorded_profile'
]


def constant_rps_profile(rps):
    """
    函数作用：生成固定 RPS 的请求速率函数。
    关键流程：
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：rps：每秒请求数，用于控制请求生成强度。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    while True:
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield rps


def sine_rps_profile(env: Environment, max_rps, period):
    """
    函数作用：生成按正弦曲线波动的请求速率函数。
    关键流程：
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；max_rps：表示 max、rps，在当前业务流程中作为输入参数、状态字段或计算结果使用。；period：表示 period，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    div = period / (2 * np.pi)  

    x = 0
    y = -1

    while True:
        if env.now == x and y >= 0:
            
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield y

        x = env.now
        y = math.sin(x / div)

        
        y = (y + 1) / 2
        y = y * max_rps

        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield y


def randomwalk_rps_profile(mu, sigma, max_rps, min_rps=0):
    """
    函数作用：生成随机游走形式的请求速率函数。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：mu：表示 mu，在当前业务流程中作为输入参数、状态字段或计算结果使用。；sigma：表示 sigma，在当前业务流程中作为输入参数、状态字段或计算结果使用。；max_rps：表示 max、rps，在当前业务流程中作为输入参数、状态字段或计算结果使用。；min_rps：表示 min、rps，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    while True:
        nmu = random.normalvariate(mu, sigma)

        
        if nmu >= max_rps:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield max_rps
        elif nmu <= min_rps:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield min_rps
        else:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield nmu
            mu = nmu


def static_arrival_profile(rps_generator, max_ia=math.inf):
    """
    函数作用：按固定间隔生成请求到达时间。
    关键流程：
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：rps_generator：表示 rps、generator，在当前业务流程中作为输入参数、状态字段或计算结果使用。；max_ia：表示 max、ia，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    while True:
        rps = next(rps_generator)
        if rps == 0:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield max_ia

        ia = 1 / rps
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield min(ia, max_ia)


def expovariate_arrival_profile(rps_generator, scale=1.0, max_ia=math.inf):
    """
    函数作用：按指数分布生成随机请求到达时间。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：rps_generator：表示 rps、generator，在当前业务流程中作为输入参数、状态字段或计算结果使用。；scale：执行时间缩放因子。；max_ia：表示 max、ia，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    while True:
        lam = next(rps_generator)
        ia = random.expovariate(lam) if lam > 0 else 1
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield min(ia * scale, max_ia)


def pre_recorded_profile(file: str):
    """
    函数作用：从预录制的到达间隔列表重放请求模式。
    关键流程：
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：file：表示 file，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    with open(file, 'rb') as fd:
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from pickle.load(fd)


def function_trigger(env: Environment, deployment: FunctionDeployment, ia_generator, max_requests=None):
    """
    函数作用：按请求到达事件触发 FaaS 函数调用。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
    - 触发函数调用并等待响应，用于工作负载生成或复合调用流程。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；deployment：函数部署对象，包含函数定义、容器规格和伸缩配置。；ia_generator：表示 ia、generator，在当前业务流程中作为输入参数、状态字段或计算结果使用。；max_requests：最大并发请求数，用于计算队列拥塞或性能退化。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    try:
        if max_requests is None:
            while True:
                ia = next(ia_generator)
                # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
                yield env.timeout(ia)
                # 请求触发：把生成的请求交给 FaaS 系统执行。
                env.process(env.faas.invoke(FunctionRequest(deployment.name)))
        else:
            for _ in range(max_requests):
                ia = next(ia_generator)
                # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
                yield env.timeout(ia)
                # 请求触发：把生成的请求交给 FaaS 系统执行。
                env.process(env.faas.invoke(FunctionRequest(deployment.name)))

    except simpy.Interrupt:
        pass
    except StopIteration:
        logging.error(f'{deployment.name} gen has finished')


def run_arrival_profile(env, ia_gen, until):
    """
    函数作用：执行一个到达模型并持续产生函数请求。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
    - 整理为表格数据，服务于后续实验分析。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；ia_gen：表示 ia、gen，在当前业务流程中作为输入参数、状态字段或计算结果使用。；until：表示 until，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    x = list()
    y = list()

    def event_generator():
        """
        函数作用：处理 event、generator 相关业务逻辑。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        while True:
            ia = next(ia_gen)
            x.append(env.now)
            y.append(ia)
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(ia)

    then = time.time()
    env.process(event_generator())
    env.run(until=until)
    print('simulating %d events took %.2f sec' % (len(x), time.time() - then))

    df = pd.DataFrame(data={'simtime': x, 'ia': y}, index=pd.DatetimeIndex(pd.to_datetime(x, unit='s', origin='unix')))
    return df


def save_requests(profile, duration, file: str, env: simpy.Environment = None):
    """
    函数作用：把生成的请求到达序列保存到文件，便于复现实验。
    参数：profile：实验 profile 名称或配置，用于选择函数集合和负载类型。；duration：实验持续时间。；file：表示 file，在当前业务流程中作为输入参数、状态字段或计算结果使用。；env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    if env is None:
        env = simpy.Environment()
    with open(file, 'wb') as fd:
        df = run_arrival_profile(env, profile(env), until=duration)
        ias = list(df['ia'])
        pickle.dump(ias, fd)
