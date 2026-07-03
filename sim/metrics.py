"""
文件作用：仿真指标记录中心，将部署、调度、调用、资源、网络、生命周期等事件写成结构化记录，便于导出 DataFrame 分析。
主要类：Metrics。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
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
    类作用：仿真指标收集器，集中记录部署、调度、调用、网络、资源和生命周期事件。
    核心字段：invocations：按函数或副本累计的调用计数。；total_invocations：全局累计调用次数。；last_invocation：函数最近一次调用时间，用于 idler 判断空闲。；utilization：资源利用率记录缓存。。
    核心方法：__init__、log、log_function_deployment、log_function_definition、log_function_replica、log_flow、log_network、log_scaling、log_invocation、log_fet、log_function_resource_utilization、log_resource_utilization 等。
    """
    # 字段说明：invocations：按函数或副本累计的调用计数。
    invocations: Dict[str, int]
    # 字段说明：total_invocations：全局累计调用次数。
    total_invocations: int
    # 字段说明：last_invocation：函数最近一次调用时间，用于 idler 判断空闲。
    last_invocation: Dict[str, float]
    # 字段说明：utilization：资源利用率记录缓存。
    utilization: Dict[str, Dict[str, float]]

    def __init__(self, env: Environment, log: RuntimeLogger = None) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：env、invocations、last_invocation、logger、total_invocations、utilization。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；log：表示 log，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env: Environment = env
        # 字段说明：self.logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
        self.logger: RuntimeLogger = log or NullLogger()
        # 字段说明：self.total_invocations：全局累计调用次数。
        self.total_invocations = 0
        # 字段说明：self.invocations：按函数或副本累计的调用计数。
        self.invocations = defaultdict(int)
        # 字段说明：self.last_invocation：函数最近一次调用时间，用于 idler 判断空闲。
        self.last_invocation = defaultdict(int)
        # 字段说明：self.utilization：资源利用率记录缓存。
        self.utilization = defaultdict(lambda: defaultdict(float))

    def log(self, metric, value, **tags):
        """
        函数作用：写入一条结构化运行记录。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：metric：表示 metric，在当前业务流程中作为输入参数、状态字段或计算结果使用。；value：写入资源表或配置表的具体数值。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.logger.log(metric, value, **tags)

    def log_function_deployment(self, fn: FunctionDeployment):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：fn：函数定义对象或函数名。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
        record = {'name': fn.name}
        self.log('function_deployments', record, type='deploy')

    def log_function_definition(self, fn_name: str, fn: FunctionContainer):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：fn_name：目标函数名称。；fn：函数定义对象或函数名。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        record = {'name': fn_name, 'image': fn.image}
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        image_state = self.env.cluster.image_states[fn.image]
        for arch, size in image_state.size.items():
            record[f'size_{arch}'] = size

            self.log('functions', record, type='deploy')

    def log_function_replica(self, replica: FunctionReplica):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        for container in replica.pod.spec.containers:
            record = {'name': replica.function.name, 'pod': replica.pod.name, 'image': container.image}
            # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
            
            
            

            self.log('function_replicas', record, replica_id=id(replica))

    def log_flow(self, num_bytes, duration, source, sink, action_type):
        """
        函数作用：记录一次网络流传输事件。
        参数：num_bytes：表示 num、bytes，在当前业务流程中作为输入参数、状态字段或计算结果使用。；duration：实验持续时间。；source：源节点或源数据对象，用于网络传输和拓扑构造。；sink：表示 sink，在当前业务流程中作为输入参数、状态字段或计算结果使用。；action_type：表示 action、type，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('flow', value={'bytes': num_bytes, 'duration': duration},
                 source=source.name, sink=sink.name, action_type=action_type)

    def log_network(self, num_bytes, data_type, link):
        """
        函数作用：记录网络状态或网络传输指标。
        参数：num_bytes：表示 num、bytes，在当前业务流程中作为输入参数、状态字段或计算结果使用。；data_type：表示 data、type，在当前业务流程中作为输入参数、状态字段或计算结果使用。；link：表示 link，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        tags = dict(link.tags)
        tags['data_type'] = data_type

        self.log('network', num_bytes, **tags)

    def log_scaling(self, function_name, replicas):
        """
        函数作用：记录一次伸缩动作的函数名、副本数变化和触发原因。
        参数：function_name：目标函数名称。；replicas：副本数量或副本列表。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('scale', replicas, function_name=function_name)

    def log_invocation(self, function_name, function_image, node_name, t_wait, t_start, t_exec, replica_id, **kwargs):
        """
        函数作用：记录一次函数调用的排队时间、执行时间、节点和返回码。
        参数：function_name：目标函数名称。；function_image：表示 function、image，在当前业务流程中作为输入参数、状态字段或计算结果使用。；node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。；t_wait：请求等待可用副本或排队的耗时。；t_start：表示 t、start，在当前业务流程中作为输入参数、状态字段或计算结果使用。；t_exec：函数主体执行耗时。；replica_id：表示 replica、id，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        function = self.env.faas.get_function_index()[function_image]
        mem = function.get_resource_requirements().get('memory')

        self.log('invocations', {'t_wait': t_wait, 't_exec': t_exec, 't_start': t_start, 'memory': mem, **kwargs},
                 function_name=function_name,
                 function_image=function_image, node=node_name, replica_id=replica_id)

    def log_fet(self, function_name, function_image, node_name, t_fet_start, t_fet_end, replica_id, request_id,
                **kwargs):
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        """
        函数作用：记录对应业务事件到指标系统。
        参数：function_name：目标函数名称。；function_image：表示 function、image，在当前业务流程中作为输入参数、状态字段或计算结果使用。；node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。；t_fet_start：表示 t、fet、start，在当前业务流程中作为输入参数、状态字段或计算结果使用。；t_fet_end：表示 t、fet、end，在当前业务流程中作为输入参数、状态字段或计算结果使用。；replica_id：表示 replica、id，在当前业务流程中作为输入参数、状态字段或计算结果使用。；request_id：函数调用请求的唯一编号。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('fets', {'t_fet_start': t_fet_start, 't_fet_end': t_fet_end, **kwargs},
                 function_name=function_name,
                 function_image=function_image, node=node_name, replica_id=replica_id, request_id=request_id)

    def log_function_resource_utilization(self, replica: FunctionReplica, utilization: ResourceUtilization):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。；utilization：资源利用率记录缓存。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        node = replica.node
        copy = utilization.copy()
        resources = self.__calculate_util(node.capacity, copy)
        self.log('function_utilization', resources, node=node.name, replica_id=id(replica))

    def log_resource_utilization(self, node_name: str, capacity: Capacity, utilization: ResourceUtilization):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。；capacity：表示 capacity，在当前业务流程中作为输入参数、状态字段或计算结果使用。；utilization：资源利用率记录缓存。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        resources = self.__calculate_util(capacity, utilization)
        self.log('node_utilization', resources, node=node_name)

    def __calculate_util(self, capacity, utilization):
        """
        函数作用：处理 calculate、util 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：capacity：表示 capacity，在当前业务流程中作为输入参数、状态字段或计算结果使用。；utilization：资源利用率记录缓存。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：记录函数请求开始执行的时间点。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。；replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.invocations[replica.function.name] += 1
        self.total_invocations += 1
        self.last_invocation[replica.function.name] = self.env.now

    def log_stop_exec(self, request: FunctionRequest, replica: FunctionReplica, **kwargs):
        """
        函数作用：记录函数请求执行结束的时间点。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。；replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        pass

    def log_deploy(self, replica: FunctionReplica):
        """
        函数作用：记录副本部署阶段开始事件。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('replica_deployment', 'deploy', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_startup(self, replica: FunctionReplica):
        """
        函数作用：记录副本启动阶段事件。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('replica_deployment', 'startup', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_setup(self, replica: FunctionReplica):
        """
        函数作用：记录副本 setup 阶段事件。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('replica_deployment', 'setup', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_finish_deploy(self, replica: FunctionReplica):
        """
        函数作用：记录副本部署完成事件。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('replica_deployment', 'finish', function_name=replica.function.name, node_name=replica.node.name,
                 replica_id=id(replica))

    def log_teardown(self, replica: FunctionReplica):
        """
        函数作用：记录副本销毁阶段事件。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        name = replica.fn_name
        node_name = replica.node.name
        self.log('replica_deployment', 'teardown', function_name=name, node_name=node_name,
                 replica_id=id(replica))

    def log_function_deployment_lifecycle(self, fn: FunctionDeployment, event: str):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：fn：函数定义对象或函数名。；event：表示 event，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.log('function_deployment_lifecycle', event, name=fn.name, function_id=id(fn))

    def log_queue_schedule(self, replica: FunctionReplica):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        name = replica.fn_name
        image = replica.image
        self.log('schedule', 'queue', function_name=name, image=image,
                 replica_id=id(replica))

    def log_start_schedule(self, replica: FunctionReplica):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        name = replica.fn_name
        image = replica.image
        self.log('schedule', 'start', function_name=name, image=image,
                 replica_id=id(replica))

    def log_finish_schedule(self, replica: FunctionReplica, result: SchedulingResult):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。；result：表示 result，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        fn = replica.container
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'deploy', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def log_function_suspend(self, replica: FunctionReplica):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        fn = replica.container
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'suspend', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def log_function_remove(self, replica: FunctionReplica):
        """
        函数作用：记录对应业务事件到指标系统。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        fn = replica.function
        image = replica.image
        name = replica.fn_name
        self.log('function_deployment', 'remove', name=name, image=image, function_id=id(fn),
                 node=replica.node.name)

    def get(self, name, **tags):
        """
        函数作用：读取指定名称的内部对象、指标表或资源项。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：name：对象名称。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.logger.get(name, **tags)

    @property
    def clock(self):
        """
        函数作用：返回指标记录所使用的时钟对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.clock

    @property
    def records(self):
        """
        函数作用：返回当前累计的结构化指标记录。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.logger.records

    def extract_dataframe(self, measurement: str):
        """
        函数作用：把内部指标记录整理为 Pandas DataFrame 结果表。
        关键流程：
        - 整理为表格数据，服务于后续实验分析。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：measurement：指标记录的类型名称。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
