"""
轻量结构化日志抽象。

本模块定义仿真时钟、墙钟、结构化 Record 和 RuntimeLogger。指标系统可以把不同事件写成 measurement + fields + tags 的统一记录，后续再导出 DataFrame 或打印。
"""

from datetime import datetime, timedelta
from typing import Dict, NamedTuple


class Clock:
    """
    时间源接口。

    RuntimeLogger 通过 Clock 获取当前时间；具体实现可以是墙钟或仿真时钟。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def now(self) -> datetime:
        """
        返回当前时间。

        这是时间源接口，子类可以返回真实墙钟时间，也可以返回由仿真时间换算出的时间。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        raise NotImplementedError()


class WallClock(Clock):

    """
    真实墙钟时间源。

    now() 返回 datetime.now()，适合非仿真上下文或调试输出。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def now(self) -> datetime:
        """
        返回真实系统时间 datetime.now()。

        返回说明：返回值类型标注为 datetime，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return datetime.now()


class Record(NamedTuple):
    """
    结构化日志记录。

    一条记录由 measurement、time、fields 和 tags 组成，方便后续转换为 DataFrame。

    重要字段：
    - measurement: 指标名称，也就是一类日志记录的 measurement。
    - time: 记录发生的时间戳，可以来自墙钟或仿真时钟。
    - fields: 指标字段字典，保存数值型或结构化观测值。
    - tags: 指标标签字典，用于区分函数、镜像、节点、动作类型等维度。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    measurement: str
    time: int
    fields: Dict
    tags: Dict


class SimulatedClock(Clock):
    """
    仿真时钟时间源。

    把 env.now 映射到从 start 开始的 datetime，使日志时间戳与仿真时间一致。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - start: 仿真时钟对应的真实起始时间，env.now 会在此基础上换算成 datetime。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self, env, start: datetime = None) -> None:
        """
        初始化 SimulatedClock 对象。

        主要建立字段：env、start。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。
        - start: start 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：datetime。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.env = env
        self.start = start or datetime.now()

    def now(self):
        """
        返回当前仿真时间对应的 datetime。

        内部用 env.now 作为秒数偏移，并委托 from_simtime 完成换算。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.from_simtime(self.env.now)

    def from_simtime(self, seconds) -> datetime:
        """
        把仿真秒数转换为 datetime。

        返回 start + timedelta(seconds=seconds)，用于让日志时间戳和 SimPy 时间保持一致。

        参数说明：
        - seconds: 仿真时间秒数。

        返回说明：返回值类型标注为 datetime，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.start + timedelta(seconds=seconds)


class RuntimeLogger:
    """
    结构化运行日志收集器。

    将标量或字典值写成 Record，并保存到 records 列表中供 Metrics 导出。

    重要字段：
    - records: RuntimeLogger 已收集的结构化日志记录列表。
    - clock: 日志时间源，可以是墙钟或仿真时钟。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, clock=None) -> None:
        """
        初始化 RuntimeLogger 对象。

        主要建立字段：records、clock。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - clock: 日志时间源对象。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.records = list()
        self.clock = clock or WallClock()

    def get(self, name, **tags):
        """
        创建一个指标写入回调。

        返回的 lambda 接收 value，并使用预先绑定的 measurement 和 tags 调用 log。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - **tags: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return lambda x: self.log(name, x, None, **tags)

    def log(self, metric, value, time=None, **tags):
        """
        把指标值转换成结构化 Record。

        字典 value 会原样作为 fields；非字典 value 会包装成 {"value": value}。未传入 time 时使用当前 Clock 时间。

        参数说明：
        - metric: 指标 measurement 名称。
        - value: 要记录或累加的数值。
        - time: time 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - **tags: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：日志记录不影响仿真控制流，但会影响实验输出、绘图和后续统计。
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
        把 Record 追加到内存记录列表。

        子类可以覆盖该方法实现打印、持久化或过滤。

        参数说明：
        - record: 结构化日志 Record。 类型标注：Record。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.records.append(record)

    def _now(self):
        """
        读取当前日志时间。

        实际时间来源由 self.clock 决定。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.clock.now()


class NullLogger(RuntimeLogger):
    """
    空日志器。

    忽略所有 log() 调用，适合关闭指标输出或测试无副作用路径。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def log(self, name, value, time=None, **tags):
        """
        忽略一条日志记录。

        用于关闭指标输出，同时保持调用方代码不需要分支判断。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - value: 要记录或累加的数值。
        - time: time 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - **tags: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：日志记录不影响仿真控制流，但会影响实验输出、绘图和后续统计。
        """
        pass


class PrintLogger(RuntimeLogger):

    """
    打印型日志器。

    在保存 Record 的同时打印出来，适合调试小规模实验。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def _store_record(self, record: Record):
        """
        保存 Record 并打印到标准输出。

        适合调试小规模仿真，避免额外写导出代码。

        参数说明：
        - record: 结构化日志 Record。 类型标注：Record。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super()._store_record(record)
        print('[log]', record)
