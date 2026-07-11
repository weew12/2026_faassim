"""
请求到达模型与工作负载生成器。

本模块提供固定 RPS、正弦波、随机游走、指数分布、预录制重放等到达模型，并把到达间隔转换为 SimPy 进程中的函数调用请求。

阅读建议：先区分 RPS 生成器和到达间隔生成器，再看 function_trigger 如何提交请求。
"""

from __future__ import annotations

import logging
import math
import pickle
import random
import time
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import simpy

if TYPE_CHECKING:
    from sim.core import Environment
    from sim.faas import FunctionDeployment

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
    生成固定 RPS 曲线。

    这是一个无限生成器，每次迭代都返回同一个 rps 值。通常先传给 static_arrival_profile 或 expovariate_arrival_profile，再由这些函数把 RPS 转换为请求到达间隔。

    参数说明：
    - rps: 每秒请求数。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    while True:
        yield rps


def sine_rps_profile(env: Environment, max_rps, period):
    """
    生成随仿真时间呈正弦变化的 RPS 曲线。

    env.now 决定当前相位，max_rps 决定峰值，period 决定完整波形周期。返回值始终被映射到 0 到 max_rps 之间，适合模拟早晚高峰一类周期性负载。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - max_rps: RPS 曲线峰值。
    - period: 正弦 RPS 曲线的周期。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    div = period / (2 * np.pi)  

    x = 0
    y = -1

    while True:
        if env.now == x and y >= 0:
            
            yield y

        x = env.now
        y = math.sin(x / div)

        
        y = (y + 1) / 2
        y = y * max_rps

        yield y


def randomwalk_rps_profile(mu, sigma, max_rps, min_rps=0):
    """
    生成随机游走形式的 RPS 曲线。

    每一步从当前均值附近采样新值，并用 min_rps 和 max_rps 截断边界。它适合模拟不规则但相邻时刻有关联的业务流量。

    参数说明：
    - mu: 随机游走当前均值。
    - sigma: 随机扰动标准差。
    - max_rps: RPS 曲线峰值。
    - min_rps: 随机游走允许的最小 RPS。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    while True:
        nmu = random.normalvariate(mu, sigma)

        
        if nmu >= max_rps:
            yield max_rps
        elif nmu <= min_rps:
            yield min_rps
        else:
            yield nmu
            mu = nmu


def static_arrival_profile(rps_generator, max_ia=math.inf):
    """
    把 RPS 曲线转换为固定到达间隔曲线。

    若当前 RPS 为 r，则间隔为 1/r；若 RPS 为 0，则返回 max_ia。调用方通常对返回值执行 env.timeout(ia)，从而按仿真时间触发请求。

    参数说明：
    - rps_generator: RPS 生成器，每次产生当前请求速率。
    - max_ia: 最大到达间隔，用于限制低负载或 0 RPS 时的等待时间。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    while True:
        rps = next(rps_generator)
        if rps == 0:
            yield max_ia

        ia = 1 / rps
        yield min(ia, max_ia)


def expovariate_arrival_profile(rps_generator, scale=1.0, max_ia=math.inf):
    """
    把 RPS 曲线转换为泊松到达间隔曲线。

    每次读取当前 lambda，然后用 random.expovariate(lambda) 采样间隔；scale 用于整体拉伸或压缩时间，max_ia 用于限制最大间隔。

    参数说明：
    - rps_generator: RPS 生成器，每次产生当前请求速率。
    - scale: 时间缩放因子或扩缩容数量，具体取决于当前函数。
    - max_ia: 最大到达间隔，用于限制低负载或 0 RPS 时的等待时间。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    while True:
        lam = next(rps_generator)
        ia = random.expovariate(lam) if lam > 0 else 1
        yield min(ia * scale, max_ia)


def pre_recorded_profile(file: str):
    """
    从 pickle 文件重放预先保存的到达间隔序列。

    文件内容应当是可迭代的间隔列表或生成器数据。该函数用 yield from 逐个返回间隔，适合复现实验工作负载。

    参数说明：
    - file: 输入或输出文件路径。 类型标注：str。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    with open(file, 'rb') as fd:
        yield from pickle.load(fd)


def function_trigger(env: Environment, deployment: FunctionDeployment, ia_generator, max_requests=None):
    """
    按到达间隔持续触发函数请求。

    每次从 ia_generator 读取一个间隔，先等待 env.timeout(ia)，再启动 env.faas.invoke(FunctionRequest(...))。max_requests 为 None 时无限运行，否则只发送指定数量请求。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - deployment: FunctionDeployment，表示一个已部署或待部署函数。 类型标注：FunctionDeployment。
    - ia_generator: 到达间隔生成器，每次产生下一次请求前需要等待的时间。
    - max_requests: 最多触发的请求数量，None 表示持续触发。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

    业务流程：这是工作负载进入系统的入口，生成请求但不直接等待请求完成。
    """
    # 只有真正向 FaaS 系统发送请求时才加载完整领域模型。这样仅使用
    # RPS/到达曲线工具的分析脚本无需同时安装调度、回归模型等重依赖。
    from sim.faas import FunctionRequest

    try:
        if max_requests is None:
            while True:
                ia = next(ia_generator)
                yield env.timeout(ia)
                # 请求触发：把生成的请求交给 FaaS 系统执行。
                env.process(env.faas.invoke(FunctionRequest(deployment.name)))
        else:
            for _ in range(max_requests):
                ia = next(ia_generator)
                yield env.timeout(ia)
                # 请求触发：把生成的请求交给 FaaS 系统执行。
                env.process(env.faas.invoke(FunctionRequest(deployment.name)))

    except simpy.Interrupt:
        pass
    except StopIteration:
        logging.error(f'{deployment.name} gen has finished')


def run_arrival_profile(env, ia_gen, until):
    """
    在独立 SimPy 环境中试跑到达间隔生成器。

    函数会记录每次事件发生的仿真时间和间隔，运行到 until 后返回 DataFrame，便于检查生成的流量曲线是否合理。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
    - ia_gen: 到达间隔生成器。
    - until: 试跑到达模型的截止仿真时间。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    x = list()
    y = list()

    def event_generator():
        """
        SimPy 协程：event_generator。

        函数中的 yield/yield from 会把控制权交还给仿真环境；调用方应使用 yield from 等待完成，或使用 env.process(...) 作为后台进程启动。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        while True:
            ia = next(ia_gen)
            x.append(env.now)
            y.append(ia)
            yield env.timeout(ia)

    then = time.time()
    env.process(event_generator())
    env.run(until=until)
    print('simulating %d events took %.2f sec' % (len(x), time.time() - then))

    df = pd.DataFrame(data={'simtime': x, 'ia': y}, index=pd.DatetimeIndex(pd.to_datetime(x, unit='s', origin='unix')))
    return df


def save_requests(profile, duration, file: str, env: simpy.Environment = None):
    """
    把某个到达模型生成的请求间隔保存到 pickle 文件。

    profile 应是接收 env 并返回间隔生成器的函数。保存后的文件可由 pre_recorded_profile 读取，用于复现实验。

    参数说明：
    - profile: 请求到达模型函数。
    - duration: 仿真持续时间或采样持续时间。
    - file: 输入或输出文件路径。 类型标注：str。
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：simpy.Environment。

    返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
    """
    if env is None:
        env = simpy.Environment()
    with open(file, 'wb') as fd:
        df = run_arrival_profile(env, profile(env), until=duration)
        ias = list(df['ia'])
        pickle.dump(ias, fd)
