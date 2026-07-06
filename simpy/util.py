"""
SimPy 工具函数。

本文件提供与进程编排相关的辅助函数。它不改变核心事件机制，而是把常见的
事件组合写法封装成可复用函数：

- ``start_delayed`` —— 延迟启动某个进程；
- ``subscribe_at`` —— 让当前活动进程订阅某个事件，被订阅事件触发时通过
  ``Interrupt`` 唤醒订阅者。

faas-sim 衔接：
- ``start_delayed`` 适合"延迟创建副本"、"延迟启动监控任务"等场景；
- ``subscribe_at`` 适合"订阅另一个进程结束事件"等场景，比直接 ``yield proc``
  更显式，因为通过 Interrupt 唤醒会让订阅者无法错过时序。
"""

from typing import Generator

from simpy.core import Environment, SimTime
from simpy.events import Event, Process, ProcessGenerator


def start_delayed(
    env: Environment, generator: ProcessGenerator, delay: SimTime
) -> Process:
    """
    返回一个辅助进程，该进程先等待 ``delay``，再启动并返回目标 ``Process``。

    实现思路：构造一个内部生成器 ``starter``，先 ``yield env.timeout(delay)``，再
    调用 ``env.process(generator)`` 把目标生成器包装为 ``Process``，并把该
    ``Process`` 作为 ``starter`` 的返回值（即 ``StopIteration.value``）。

    调用方拿到的"延迟启动器"本身也是一个 ``Process``，因此可以：

    - ``yield start_delayed(...)`` 等待其结束（返回时即目标进程已创建）；
    - ``start_delayed(...).interrupt(...)`` 在延迟期内取消启动。

    注意：``delay`` 必须严格大于 0，否则抛 ``ValueError``，避免出现"零延迟启动器"
    这种没有实际意义的退化用法。
    """
    if delay <= 0:
        raise ValueError(f'delay(={delay}) must be > 0.')

    def starter() -> Generator[Event, None, Process]:
        # 1) 先 sleep delay；这会让 starter 进程挂起到延迟到期为止。
        yield env.timeout(delay)
        # 2) 到期后再把目标生成器包装为 Process 并启动。
        proc = env.process(generator)
        # 3) 通过 return 把 proc 作为 starter 的"返回值"，调用方
        #    ``yield start_delayed(...)`` 时就能拿到 proc。
        return proc

    # 把 starter 立刻包装为 Process 返回。注意此时 starter 还没真正"启动"——
    # 它内部第一个动作是 ``yield env.timeout(delay)``，所以 Process 创建后
    # 在事件队列里的下一个事件就是 delay 后的那个 timeout 事件。
    return env.process(starter())


def subscribe_at(event: Event) -> None:
    """
    让当前活动进程订阅某个事件；当目标事件完成时，订阅进程会被 ``Interrupt`` 唤醒。

    实现思路：
    1. 取 ``env.active_process`` 作为订阅者，**因此必须在活动进程内部调用**。
    2. 构造内部信号生成器 ``signaller``：先 ``yield event`` 等待被订阅事件完成，
       再判断订阅者是否仍存活，若存活就 ``interrupt((event, result))``。
    3. 把 ``signaller`` 包装为 Process 提交到环境队列。

    异常路径：若 ``event`` 已经被处理（``callbacks is None``），说明订阅得太晚，
    此时直接抛 ``RuntimeError``，避免生成一个永远等不到目标事件的孤儿进程。

    订阅者在被唤醒后通常这样处理：
        try:
            yield env.timeout(...)
        except simpy.Interrupt as i:
            signaller, result = i.cause
            # 处理订阅事件的结果
    """
    env = event.env
    # 必须有活动进程——subscribe_at 的语义是"当前进程去订阅某个事件"，没有活动
    # 进程就不知道该去中断谁。
    assert env.active_process is not None
    subscriber = env.active_process

    def signaller(signaller: Event, receiver: Process) -> ProcessGenerator:
        # 等待被订阅事件完成；yield 出来的就是 event 本身（成功/失败都会触发）。
        result = yield signaller
        # 订阅者可能已经在 signaller 完成之前结束（例如被其他中断杀掉），这时
        # 不能再 interrupt 它（Interrupt 构造时会校验 process 是否还存活）。
        if receiver.is_alive:
            # cause 用 (被订阅事件, 事件结果) 元组，订阅者按需解读。
            receiver.interrupt((signaller, result))

    # 只有事件尚未被处理时才能注册回调；否则事件已经触发了，订阅毫无意义。
    if event.callbacks is not None:
        env.process(signaller(event, subscriber))
    else:
        raise RuntimeError(f'{event} has already terminated.')