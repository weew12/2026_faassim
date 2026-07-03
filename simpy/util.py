"""
SimPy 工具函数。

本文件提供与进程编排相关的辅助函数。``start_delayed`` 用于延迟启动某个进程，
``subscribe_at`` 用于让当前进程在目标事件完成时收到中断通知。这些工具不改变核心
事件机制，而是把常见的事件组合写法封装成可复用函数。
"""

from typing import Generator

from simpy.core import Environment, SimTime
from simpy.events import Event, Process, ProcessGenerator


def start_delayed(
    env: Environment, generator: ProcessGenerator, delay: SimTime
) -> Process:
    """
    返回一个辅助进程，该进程先等待 delay，再启动并返回目标进程。
    """
    if delay <= 0:
        raise ValueError(f'delay(={delay}) must be > 0.')

    def starter() -> Generator[Event, None, Process]:
        yield env.timeout(delay)
        proc = env.process(generator)
        return proc

    return env.process(starter())


def subscribe_at(event: Event) -> None:
    """
    让当前活动进程订阅某个事件；当目标事件完成时，订阅进程会被中断唤醒。
    """
    env = event.env
    assert env.active_process is not None
    subscriber = env.active_process

    def signaller(signaller: Event, receiver: Process) -> ProcessGenerator:
        result = yield signaller
        if receiver.is_alive:
            receiver.interrupt((signaller, result))

    if event.callbacks is not None:
        env.process(signaller(event, subscriber))
    else:
        raise RuntimeError(f'{event} has already terminated.')
