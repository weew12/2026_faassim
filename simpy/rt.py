"""
SimPy 实时仿真环境。

本文件在普通离散事件环境基础上加入**墙钟时间同步**能力。它实现
``RealtimeEnvironment``，让仿真时间按指定 ``factor`` 映射到真实时间。

faas-sim 衔接：
- faas-sim 当前**默认采用普通离散事件仿真**（``simpy.Environment`` 或其子类
  ``sim.core.Environment``），跑得比真实时间快几个数量级；
- ``RealtimeEnvironment`` 是后续做数字孪生、在线协同仿真、与外部系统或人工
  观察对齐时保留的入口；
- ``factor`` 控制"仿真 1 单位 = ? 真实秒"，详见 ``step()`` 的注释。
"""

from time import monotonic, sleep

from simpy.core import EmptySchedule, Environment, Infinity, SimTime


class RealtimeEnvironment(Environment):
    """
    实时环境。它继承 ``Environment``，并在 ``step`` 前等待墙钟时间，使仿真时间
    按 ``factor`` 与真实时间保持同步。

    与父类的差异只有一处：``step()`` 被重写，在执行下一个离散事件前先 sleep 到
    对应的墙钟时刻。事件队列管理、回调执行、失败传播等核心逻辑全部沿用父类。
    """

    def __init__(
        self,
        initial_time: SimTime = 0,
        factor: float = 1.0,
        strict: bool = True,
    ):
        # 注意：这里显式调用 ``Environment.__init__`` 而非 ``super().__init__``，
        # 是为了在该类被多重继承（虽然现实中很少见）时仍能正确初始化基类。
        Environment.__init__(self, initial_time)

        # 字段：实时环境同步时的仿真起始时间。``sync()`` 调用后只重置 real_start，
        # 不重置 env_start，因此两个基准共同决定了"仿真起点 → 墙钟起点"的偏移。
        self.env_start = initial_time
        # 字段：实时环境同步时的真实墙钟起始时间。``monotonic()`` 不会因系统时间
        # 调整而回退，比 ``time.time()`` 更适合作为同步基准。
        self.real_start = monotonic()
        # 字段：仿真时间到真实秒数的换算因子。factor=0.001 表示仿真 1 秒对应
        # 真实 1 毫秒（快 1000 倍）；factor=60 表示仿真 1 秒对应真实 60 秒（放慢）。
        self._factor = factor
        # 字段：是否在仿真落后墙钟时间过多时抛出错误。生产环境建议 True，避免
        # sleep 时间变成负数后陷入忙等。
        self._strict = strict

    @property
    def factor(self) -> float:
        """
        返回一个仿真时间单位对应的真实秒数。
        """
        return self._factor

    @property
    def strict(self) -> bool:
        """
        返回是否启用严格实时模式。
        """
        return self._strict

    def sync(self) -> None:
        """
        把当前仿真时间与当前真实时间重新对齐。

        适用场景：跑了一段非仿真逻辑后希望重新把仿真拉回墙钟节奏（例如刚做完一次
        外部 IO、刚和真实节点同步了状态）。重置后 ``real_start`` 从 ``now()`` 开始
        重新计时，``env_start`` 不变。
        """
        self.real_start = monotonic()

    def step(self) -> None:
        """
        在执行下一个离散事件前等待对应墙钟时间，必要时检查仿真是否落后过多。

        执行步骤：
        1. 取下一个事件的仿真时间；若队列空，抛 ``EmptySchedule`` 让 ``run`` 正常退出。
        2. 计算它应该触发的墙钟时刻：``real_time = real_start + (evt_time - env_start) * factor``。
        3. ``strict`` 模式下，若当前墙钟已经超过 ``real_time`` 超过 ``factor`` 秒，
           说明仿真执行速度跟不上墙钟，直接抛 ``RuntimeError``，避免后续 sleep 负
           数陷入忙等。
        4. 否则用循环 ``sleep`` 把墙钟推进到 ``real_time``（短于 sleep 粒度的剩余
           时间会让循环退化为忙等——这是 Python sleep 的固有限制）。
        5. 调用父类 ``Environment.step(self)`` 执行事件本体逻辑。

        注意：父类 ``step`` 仍然负责推进 ``_now``、执行回调、维护事件队列，
        本类只在外层加了一段"等墙钟"逻辑。
        """
        evt_time = self.peek()

        if evt_time is Infinity:
            # 队列空意味着没有下一个事件，让 ``run`` 捕获 ``EmptySchedule`` 即可。
            raise EmptySchedule

        # 计算"事件 evt_time 应该发生的墙钟时刻"。
        real_time = self.real_start + (evt_time - self.env_start) * self.factor

        if self.strict and monotonic() - real_time > self.factor:
            # 已经落后超过一个 factor 单位，说明前面的业务太慢或 wall-clock 调度
            # 抖动过大。直接抛错比 sleep(负数) 反复空转更友好。
            delta = monotonic() - real_time
            raise RuntimeError(f'Simulation too slow for real time ({delta:.3f}s).')

        # 循环 sleep 直到墙钟到达 real_time。理论上应该一次 sleep(delta) 就够，
        # 但 sleep 的实际睡眠时长可能略短于请求值，所以循环修正。
        while True:
            delta = real_time - monotonic()
            if delta <= 0:
                break
            sleep(delta)

        # 走到这里表示墙钟已经追上目标时刻，让父类完成事件处理。
        Environment.step(self)