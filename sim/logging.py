"""
文件作用：轻量运行日志抽象，统一墙上时钟/仿真时钟记录格式，为运行过程输出结构化 Record。
主要类：Clock、WallClock、Record、SimulatedClock、RuntimeLogger、NullLogger、PrintLogger。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

from datetime import datetime, timedelta
from typing import Dict, NamedTuple


class Clock:
    """
    类作用：Clock 类，封装 clock 相关状态和业务操作。
    核心方法：now。
    """
    def now(self) -> datetime:
        """
        函数作用：处理 now 相关业务逻辑。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError()


class WallClock(Clock):

    """
    类作用：WallClock 类，封装 wall、clock 相关状态和业务操作。
    继承关系：Clock。
    核心方法：now。
    """
    def now(self) -> datetime:
        """
        函数作用：处理 now 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return datetime.now()


class Record(NamedTuple):
    """
    类作用：Record 类，封装 record 相关状态和业务操作。
    继承关系：NamedTuple。
    核心字段：measurement：指标记录的类型名称。；time：记录产生的时间戳。；fields：指标记录中的数值字段。；tags：指标记录中的维度标签。。
    """
    # 字段说明：measurement：指标记录的类型名称。
    measurement: str
    # 字段说明：time：记录产生的时间戳。
    time: int
    # 字段说明：fields：指标记录中的数值字段。
    fields: Dict
    # 字段说明：tags：指标记录中的维度标签。
    tags: Dict


class SimulatedClock(Clock):
    """
    类作用：SimulatedClock 类，封装 simulated、clock 相关状态和业务操作。
    继承关系：Clock。
    核心方法：__init__、now、from_simtime。
    """

    def __init__(self, env, start: datetime = None) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：env、start。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；start：函数调用或生命周期阶段开始时间。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.start：函数调用或生命周期阶段开始时间。
        self.start = start or datetime.now()

    def now(self):
        """
        函数作用：处理 now 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.from_simtime(self.env.now)

    def from_simtime(self, seconds) -> datetime:
        """
        函数作用：处理 from、simtime 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：seconds：表示 seconds，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.start + timedelta(seconds=seconds)


class RuntimeLogger:
    """
    类作用：RuntimeLogger 类，封装 runtime、logger 相关状态和业务操作。
    核心方法：__init__、get、log、_store_record、_now。
    """
    def __init__(self, clock=None) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：clock、records。
        参数：clock：时间源对象，用于生成结构化记录的时间戳。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.records：结构化日志记录列表。
        self.records = list()
        # 字段说明：self.clock：时间源对象，用于生成结构化记录的时间戳。
        self.clock = clock or WallClock()

    def get(self, name, **tags):
        """
        函数作用：读取指定名称的内部对象、指标表或资源项。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：name：对象名称。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return lambda x: self.log(name, x, None, **tags)

    def log(self, metric, value, time=None, **tags):
        """
        函数作用：写入一条结构化运行记录。
        参数：metric：表示 metric，在当前业务流程中作为输入参数、状态字段或计算结果使用。；value：写入资源表或配置表的具体数值。；time：记录产生的时间戳。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if time is None:
            time = self._now()

        if type(value) == dict:
            fields = value
        else:
            fields = {
                'value': value
            }

        self._store_record(Record(metric, time, fields, tags))

    def _store_record(self, record: Record):
        """
        函数作用：处理 store、record 相关业务逻辑。
        参数：record：单条结构化日志记录，包含 measurement、time、fields 和 tags。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.records.append(record)

    def _now(self):
        """
        函数作用：处理 now 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.clock.now()


class NullLogger(RuntimeLogger):
    """
    类作用：NullLogger 类，封装 null、logger 相关状态和业务操作。
    继承关系：RuntimeLogger。
    核心方法：log。
    """

    def log(self, name, value, time=None, **tags):
        """
        函数作用：写入一条结构化运行记录。
        参数：name：对象名称。；value：写入资源表或配置表的具体数值。；time：记录产生的时间戳。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        pass


class PrintLogger(RuntimeLogger):

    """
    类作用：PrintLogger 类，封装 print、logger 相关状态和业务操作。
    继承关系：RuntimeLogger。
    核心方法：_store_record。
    """
    def _store_record(self, record: Record):
        """
        函数作用：处理 store、record 相关业务逻辑。
        参数：record：单条结构化日志记录，包含 measurement、time、fields 和 tags。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super()._store_record(record)
        print('[log]', record)
