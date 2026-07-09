"""
仿真指标记录中心。

Metrics 封装部署、调度、调用、网络、资源利用率和生命周期事件的记录逻辑，最终把运行过程转成结构化日志记录，便于实验后分析。

阅读建议：把每个 log_* 方法看成一个 measurement 的写入入口。
"""

from collections import defaultdict
from typing import Dict

import pandas as pd
from ether.core import Capacity
from skippy.core.model import SchedulingResult

from sim.core import Environment
from sim.faas import FunctionContainer, FunctionRequest, FunctionReplica, FunctionDeployment
from sim.logging import RuntimeLogger, NullLogger
from sim.resource import ResourceUtilization


class Metrics:
    """
    仿真指标记录中心。

    为部署、调度、调用、资源、网络和生命周期事件提供统一记录方法，并可按 measurement 导出 Pandas DataFrame。

    重要字段：
    - invocations: 按函数名统计的调用次数。
    - total_invocations: 全部函数调用总数。
    - last_invocation: 每个函数最后一次调用发生的仿真时间。
    - utilization: 资源利用率缓存。
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - logger: 底层 RuntimeLogger 或模块日志器。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    invocations: Dict[str, int]
    total_invocations: int
    last_invocation: Dict[str, float]
    utilization: Dict[str, Dict[str, float]]

    def __init__(self, env: Environment, log: RuntimeLogger = None) -> None:
        """
        初始化指标中心。

        保存 Environment、底层 RuntimeLogger、总调用数、按函数统计的调用数、最后调用时间和资源利用率缓存。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - log: 底层 RuntimeLogger 实例；为空时使用 NullLogger。 类型标注：RuntimeLogger。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.env: Environment = env
        self.logger: RuntimeLogger = log or NullLogger()
        self.total_invocations = 0
        self.invocations = defaultdict(int)
        self.last_invocation = defaultdict(int)
        self.utilization = defaultdict(lambda: defaultdict(float))

    def log(self, metric, value, **tags):
        """
        写入一条原始指标记录。

        metric 作为 measurement，value 作为字段值，tags 作为维度标签，实际存储由 RuntimeLogger 完成。

        参数说明：
        - metric: 指标 measurement 名称。
        - value: 要记录或累加的数值。
        - **tags: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。

        业务流程：日志记录不影响仿真控制流，但会影响实验输出、绘图和后续统计。
        """
        return self.logger.log(metric, value, **tags)

    def log_function_deployment(self, fn: FunctionDeployment):
        """
        记录函数部署定义事件。

        写入 function_deployments measurement，用于实验后查看哪些函数被部署。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        record = {'name': fn.name}
        self.log('function_deployments', record, type='deploy')

    def log_function_definition(self, fn_name: str, fn: FunctionContainer):
        """
        记录函数容器定义及镜像大小。

        方法从 Skippy image_states 中读取各架构镜像大小，并写入 functions measurement。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionContainer。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        record = {'name': fn_name, 'image': fn.image}
        image_state = self.env.cluster.image_states[fn.image]
        for arch, size in image_state.size.items():
            record[f'size_{arch}'] = size

            self.log('functions', record, type='deploy')

    def log_function_replica(self, replica: FunctionReplica):
        """
        记录函数副本与 Pod、镜像之间的绑定关系。

        每个容器都会写入 function_replicas measurement，replica_id 用于与后续生命周期事件关联。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        for container in replica.pod.spec.containers:
            record = {'name': replica.function.name, 'pod': replica.pod.name, 'image': container.image}
            
            
            

            self.log('function_replicas', record, replica_id=id(replica))

    def log_flow(self, num_bytes, duration, source, sink, action_type):
        """
        记录一次数据流传输。

        包含传输字节数、耗时、源节点、目标节点和动作类型，可用于分析镜像拉取或请求数据传输成本。

        参数说明：
        - num_bytes: 网络传输字节数。
        - duration: 仿真持续时间或采样持续时间。
        - source: 网络传输源节点或源节点名。
        - sink: 网络传输目标节点。
        - action_type: 网络传输动作类型，例如 docker_pull、download 或 upload。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('flow', value={'bytes': num_bytes, 'duration': duration},
                 source=source.name, sink=sink.name, action_type=action_type)

    def log_network(self, num_bytes, data_type, link):
        """
        记录链路级网络流量。

        方法把链路标签和 data_type 合并为 tags，并把传输字节数写入 network measurement。

        参数说明：
        - num_bytes: 网络传输字节数。
        - data_type: 网络数据类型标签，用于区分镜像、请求数据或响应数据。
        - link: 网络链路对象，提供标签和带宽等信息。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        tags = dict(link.tags)
        tags['data_type'] = data_type

        self.log('network', num_bytes, **tags)

    def log_scaling(self, function_name, replicas):
        """
        记录函数扩缩容事件。

        replicas 为正表示扩容，为负表示缩容。

        参数说明：
        - function_name: 目标函数名。
        - replicas: 副本数量或副本列表，具体由所在方法决定。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('scale', replicas, function_name=function_name)

    def log_invocation(self, function_name, function_image, node_name, t_wait, t_start, t_exec, replica_id, **kwargs):
        """
        记录一次端到端函数调用。

        字段包括等待时间、执行时间、开始时间和函数内存配置；标签包含函数名、镜像、节点和副本 ID。

        参数说明：
        - function_name: 目标函数名。
        - function_image: 函数实际运行的镜像字符串。
        - node_name: 节点名称。
        - t_wait: 请求等待时间。
        - t_start: 函数执行阶段开始的仿真时间。
        - t_exec: 函数执行耗时。
        - replica_id: 副本对象的 Python id，用于跨 measurement 关联同一个副本。
        - **kwargs: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        function = self.env.faas.get_function_index()[function_image]
        mem = function.get_resource_requirements().get('memory')

        self.log('invocations', {'t_wait': t_wait, 't_exec': t_exec, 't_start': t_start, 'memory': mem, **kwargs},
                 function_name=function_name,
                 function_image=function_image, node=node_name, replica_id=replica_id)

    def log_fet(self, function_name, function_image, node_name, t_fet_start, t_fet_end, replica_id, request_id,
                **kwargs):
        """
        记录函数执行时间窗口。

        FET 表示函数主体执行阶段的开始和结束时间，可与 invocation 的等待时间、网络时间区分分析。

        参数说明：
        - function_name: 目标函数名。
        - function_image: 函数实际运行的镜像字符串。
        - node_name: 节点名称。
        - t_fet_start: 函数执行时间窗口开始时间。
        - t_fet_end: 函数执行时间窗口结束时间。
        - replica_id: 副本对象的 Python id，用于跨 measurement 关联同一个副本。
        - request_id: 请求唯一编号，用于在历史请求中定位对应调用。
        - **kwargs: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('fets', {'t_fet_start': t_fet_start, 't_fet_end': t_fet_end, **kwargs},
                 function_name=function_name,
                 function_image=function_image, node=node_name, replica_id=replica_id, request_id=request_id)

    def log_function_resource_utilization(self, replica: FunctionReplica, utilization: ResourceUtilization):
        """
        记录单个函数副本的资源利用率。

        方法会先把资源占用转换为 CPU/内存比例，再写入 function_utilization measurement。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - utilization: 当前资源占用快照。 类型标注：ResourceUtilization。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        node = replica.node
        copy = utilization.copy()
        resources = self.__calculate_util(node.capacity, copy)
        self.log('function_utilization', resources, node=node.name, replica_id=id(replica))

    def log_resource_utilization(self, node_name: str, capacity: Capacity, utilization: ResourceUtilization):
        """
        记录节点级资源利用率。

        输入的 ResourceUtilization 会被转换为包含 cpu_util 和 mem_util 的资源快照。

        参数说明：
        - node_name: 节点名称。 类型标注：str。
        - capacity: 节点容量对象，包含 CPU 和内存上限。 类型标注：Capacity。
        - utilization: 当前资源占用快照。 类型标注：ResourceUtilization。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        resources = self.__calculate_util(capacity, utilization)
        self.log('node_utilization', resources, node=node_name)

    def __calculate_util(self, capacity, utilization):
        """
        把原始资源占用补充为利用率字段。

        CPU 使用量除以 capacity.cpu_millis 得到 cpu_util，内存使用量除以 capacity.memory 得到 mem_util，同时保留原始资源字段。

        参数说明：
        - capacity: 节点容量对象，包含 CPU 和内存上限。
        - utilization: 当前资源占用快照。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        update = {
            'cpu_util': utilization.get_resource('cpu') / capacity.cpu_millis if utilization.get_resource(
                'cpu') is not None else 0,
            'mem_util': utilization.get_resource('memory') / capacity.memory if utilization.get_resource(
                'memory') is not None else 0
        }
        resources = utilization.list_resources()
        resources.update(update)
        return resources

    def log_start_exec(self, request: FunctionRequest, replica: FunctionReplica, **kwargs):
        """
        记录函数开始执行。

        这里主要维护调用计数和 last_invocation 时间，供伸缩器和 scale-to-zero 空闲检测使用。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - **kwargs: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.invocations[replica.function.name] += 1
        self.total_invocations += 1
        self.last_invocation[replica.function.name] = self.env.now

    def log_stop_exec(self, request: FunctionRequest, replica: FunctionReplica, **kwargs):
        """
        函数执行结束钩子。

        当前实现不写指标，保留该入口是为了让更复杂的模拟器在结束阶段扩展统计逻辑。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - **kwargs: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        pass

    def log_deploy(self, replica: FunctionReplica):
        """
        记录副本 deploy 生命周期事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('replica_deployment', 'deploy', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_startup(self, replica: FunctionReplica):
        """
        记录副本 startup 生命周期事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('replica_deployment', 'startup', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_setup(self, replica: FunctionReplica):
        """
        记录副本 setup 生命周期事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('replica_deployment', 'setup', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_finish_deploy(self, replica: FunctionReplica):
        """
        记录副本完成部署并即将进入 RUNNING 的事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('replica_deployment', 'finish', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_teardown(self, replica: FunctionReplica):
        """
        记录副本 teardown 生命周期事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        name = replica.fn_name
        node_name = replica.node.name
        self.log('replica_deployment', 'teardown', function_name=name, node_name=node_name,
                 replica_id=id(replica))

    def log_function_deployment_lifecycle(self, fn: FunctionDeployment, event: str):
        """
        记录函数部署对象的生命周期事件。

        event 通常为 deploy 或 remove，用 function_id 关联同一个 FunctionDeployment。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。
        - event: 生命周期事件名称，例如 deploy、remove、startup、finish。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.log('function_deployment_lifecycle', event, name=fn.name, function_id=id(fn))

    def log_queue_schedule(self, replica: FunctionReplica):
        """
        记录副本进入调度队列。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        name = replica.fn_name
        image = replica.image
        self.log('schedule', 'queue', function_name=name, image=image,
                 replica_id=id(replica))

    def log_start_schedule(self, replica: FunctionReplica):
        """
        记录调度器开始处理副本。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        name = replica.fn_name
        image = replica.image
        self.log('schedule', 'start', function_name=name, image=image,
                 replica_id=id(replica))

    def log_finish_schedule(self, replica: FunctionReplica, result: SchedulingResult):
        """
        记录调度器完成调度。

        若没有 suggested_host，则 node_name 记录为 None，successful 为 False。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - result: 调度器返回的 SchedulingResult。 类型标注：SchedulingResult。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        if not result.suggested_host:
            node_name = 'None'
        else:
            node_name = result.suggested_host.name

        self.log('schedule', 'finish', function_name=replica.function.name, image=replica.container.image,
                 node_name=node_name,
                 successful=node_name != 'None', replica_id=id(replica))

    def log_function_deploy(self, replica: FunctionReplica):
        """
        记录函数副本部署到节点后的函数级事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        fn = replica.container
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'deploy', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def log_function_suspend(self, replica: FunctionReplica):
        """
        记录函数副本被挂起的事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        fn = replica.container
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'suspend', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def log_function_remove(self, replica: FunctionReplica):
        """
        记录函数副本被移除的事件。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        fn = replica.function
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'remove', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def get(self, name, **tags):
        """
        返回指定 measurement 和 tags 的日志写入函数。

        这是 RuntimeLogger.get 的代理，便于外部代码把某类指标绑定成回调函数。

        参数说明：
        - name: name 参数，参与当前方法的计算、查询、状态更新或流程控制。
        - **tags: 可变关键字参数，通常用于透传指标标签或扩展配置。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.logger.get(name, **tags)

    @property
    def clock(self):
        """
        返回指标日志使用的时间源。

        注意当前实现返回 self.clock，保持了原项目代码行为；读取实际底层时间源通常应查看 self.logger.clock。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.clock

    @property
    def records(self):
        """
        返回底层 RuntimeLogger 已收集的 Record 列表。

        extract_dataframe 会基于这些记录按 measurement 导出表格。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return self.logger.records

    def extract_dataframe(self, measurement: str):
        """
        按 measurement 导出 Pandas DataFrame。

        方法会把 Record 的 fields 和 tags 展平成列，并使用记录时间作为 DatetimeIndex。

        参数说明：
        - measurement: 需要导出的 measurement 名称。 类型标注：str。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        data = list()

        for record in self.records:
            if record.measurement != measurement:
                continue

            r = dict()
            r['time'] = record.time
            for k, v in record.fields.items():
                r[k] = v
            for k, v in record.tags.items():
                r[k] = v

            data.append(r)
        df = pd.DataFrame(data)

        if len(data) == 0:
            return df

        df.index = pd.DatetimeIndex(pd.to_datetime(df['time']))
        del df['time']
        return df
