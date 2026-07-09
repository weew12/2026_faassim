"""
资源状态、资源窗口与资源监控。

本模块记录函数副本在节点上的资源占用，按副本和节点聚合利用率，并通过 ResourceMonitor 周期性采样写入 MetricsServer。

阅读建议：先看 ResourceState 如何登记资源，再看 ResourceMonitor 如何周期采样。
"""

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from sim.core import Environment
from sim.faas import FunctionReplica, FaasSystem, FunctionState


class ResourceUtilization:
    """
    单个副本的资源使用集合。

    按资源名累计占用值，并提供复制、查询和空判断。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    __resources: Dict[str, float]

    def __init__(self):
        """
        初始化 ResourceUtilization 对象。

        主要建立字段：__resources。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.__resources = {}

    def put_resource(self, resource: str, value: float):
        """
        累加某类资源的占用值。

        资源名不存在时先初始化为 0，再把 value 加到当前占用上。CPU、内存、网络等资源都用同一套字典结构保存。

        参数说明：
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源登记通常在函数执行开始时发生，必须与 release/remove 逻辑配对。
        """
        if self.__resources.get(resource) is None:
            self.__resources[resource] = 0
        self.__resources[resource] += value

    def remove_resource(self, resource: str, value: float):
        """
        扣减某类资源的占用值。

        函数执行阶段结束时调用该方法释放之前登记的资源占用。

        参数说明：
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源释放通常在函数执行结束时发生，避免后续采样继续看到已结束请求的资源占用。
        """
        if self.__resources.get(resource) is None:
            self.__resources[resource] = 0
        self.__resources[resource] -= value

    def list_resources(self) -> Dict[str, float]:
        """
        返回资源占用字典的深拷贝。

        调用方拿到的是快照，修改返回值不会影响 ResourceUtilization 内部状态。

        返回说明：返回值类型标注为 Dict[str, float]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return deepcopy(self.__resources)

    def copy(self) -> 'ResourceUtilization':
        """
        复制当前资源占用对象。

        新对象拥有独立的资源字典，适合在采样窗口或指标记录中保存某一时刻的状态。

        返回说明：返回值类型标注为 'ResourceUtilization'，通常作为后续调度、执行、统计或查询流程的输入。
        """
        util = ResourceUtilization()
        util.__resources = self.list_resources()
        return util

    def get_resource(self, resource) -> Optional[float]:
        """
        读取指定资源的当前占用值。

        资源不存在时返回 None，调用方需要按业务含义决定是否当作 0 处理。

        参数说明：
        - resource: 资源名，例如 cpu、memory、net 等。

        返回说明：返回值类型标注为 Optional[float]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.__resources.get(resource)

    def is_empty(self) -> bool:
        """
        判断当前对象是否没有记录任何资源占用。

        返回说明：返回值类型标注为 bool，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return len(self.__resources) == 0


class NodeResourceUtilization:
    """
    节点级资源使用聚合。

    按 Pod/副本保存 ResourceUtilization，并可汇总节点总资源占用。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    __resources: Dict[str, ResourceUtilization]

    
    __replicas: Dict[str, FunctionReplica]

    def __init__(self):
        """
        初始化 NodeResourceUtilization 对象。

        主要建立字段：__resources、__replicas。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.__resources = {}
        self.__replicas = {}

    def put_resource(self, replica: FunctionReplica, resource: str, value: float):
        """
        为某个副本登记节点上的资源占用。

        副本以 Pod 名为键保存；不存在记录时会自动创建 ResourceUtilization。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源登记通常在函数执行开始时发生，必须与 release/remove 逻辑配对。
        """
        # 资源占用：登记函数当前阶段占用的资源。
        self.get_resource_utilization(replica).put_resource(resource, value)

    def remove_resource(self, replica: FunctionReplica, resource: str, value: float):
        """
        释放某个副本在节点上的资源占用。

        该方法只改变资源计数，不删除副本索引，因此后续监控仍可按 Pod 找到该副本。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源释放通常在函数执行结束时发生，避免后续采样继续看到已结束请求的资源占用。
        """
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        self.get_resource_utilization(replica).remove_resource(resource, value)

    def get_resource_utilization(self, replica: FunctionReplica) -> ResourceUtilization:
        """
        返回指定副本的资源占用对象。

        如果该副本首次出现，会创建空的 ResourceUtilization 并登记副本引用。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        返回说明：返回值类型标注为 ResourceUtilization，通常作为后续调度、执行、统计或查询流程的输入。
        """
        name = replica.pod.name
        util = self.__resources.get(name)
        if util is None:
            self.__resources[name] = ResourceUtilization()
            self.__replicas[name] = replica
            return self.__resources[name]
        else:
            return util

    def list_resource_utilization(self) -> List[Tuple[FunctionReplica, ResourceUtilization]]:
        """
        列出节点上所有副本及其资源占用。

        返回值是 (FunctionReplica, ResourceUtilization) 列表，供资源监控器逐个采样。

        返回说明：返回值类型标注为 List[Tuple[FunctionReplica, ResourceUtilization]]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        functions = []
        for pod_name, utilization in self.__resources.items():
            replica = self.__replicas.get(pod_name)
            functions.append((replica, utilization))
        return functions

    @property
    def total_utilization(self) -> ResourceUtilization:
        """
        汇总节点上所有副本的资源占用。

        逐个遍历副本资源字典，把同名资源加总到新的 ResourceUtilization 中。

        返回说明：返回值类型标注为 ResourceUtilization，通常作为后续调度、执行、统计或查询流程的输入。
        """
        total = ResourceUtilization()
        for _, resource_utilization in self.list_resource_utilization():
            for resource, value in resource_utilization.list_resources().items():
                # 资源占用：登记函数当前阶段占用的资源。
                total.put_resource(resource, value)
        return total


class ResourceState:
    """
    全局资源状态表。

    按节点维护 NodeResourceUtilization，提供登记、释放和查询副本资源占用的入口。

    重要字段：
    - node_resource_utilizations: node_resource_utilizations 相关的内部状态或配置；本类方法会在对应业务阶段读取或更新它。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    node_resource_utilizations: Dict[str, NodeResourceUtilization]

    def __init__(self):
        """
        初始化 ResourceState 对象。

        主要建立字段：node_resource_utilizations。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.node_resource_utilizations = {}

    def put_resource(self, function_replica: FunctionReplica, resource: str, value: float):
        """
        登记某个副本在其所在节点上的资源占用。

        方法先根据 replica.node.name 找到节点资源表，再把资源增量写入对应副本。

        参数说明：
        - function_replica: function_replica 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：FunctionReplica。
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源登记通常在函数执行开始时发生，必须与 release/remove 逻辑配对。
        """
        # 资源状态按节点分组，因此先由副本找到所在节点，再进入该节点的资源聚合表。
        node_name = function_replica.node.name
        node_resources = self.get_node_resource_utilization(node_name)
        # 资源占用：登记函数当前阶段占用的资源。
        node_resources.put_resource(function_replica, resource, value)

    def remove_resource(self, replica: 'FunctionReplica', resource: str, value: float):
        """
        释放某个副本在其所在节点上的资源占用。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：'FunctionReplica'。
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - value: 要记录或累加的数值。 类型标注：float。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：资源释放通常在函数执行结束时发生，避免后续采样继续看到已结束请求的资源占用。
        """
        node_name = replica.node.name
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        self.get_node_resource_utilization(node_name).remove_resource(replica, resource, value)

    def get_resource_utilization(self, replica: 'FunctionReplica') -> 'ResourceUtilization':
        """
        读取某个副本当前的资源占用对象。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：'FunctionReplica'。

        返回说明：返回值类型标注为 'ResourceUtilization'，通常作为后续调度、执行、统计或查询流程的输入。
        """
        node_name = replica.node.name
        return self.get_node_resource_utilization(node_name).get_resource_utilization(replica)

    def list_resource_utilization(self, node_name: str) -> List[Tuple['FunctionReplica', 'ResourceUtilization']]:
        """
        列出指定节点上所有副本的资源占用。

        参数说明：
        - node_name: 节点名称。 类型标注：str。

        返回说明：返回值类型标注为 List[Tuple['FunctionReplica', 'ResourceUtilization']]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.get_node_resource_utilization(node_name).list_resource_utilization()

    def get_node_resource_utilization(self, node_name: str) -> Optional[NodeResourceUtilization]:
        """
        返回指定节点的资源聚合对象，不存在时自动创建。

        参数说明：
        - node_name: 节点名称。 类型标注：str。

        返回说明：返回值类型标注为 Optional[NodeResourceUtilization]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        node_resources = self.node_resource_utilizations.get(node_name)
        if node_resources is None:
            # 节点第一次出现时延迟创建资源表，避免初始化阶段必须遍历完整拓扑。
            self.node_resource_utilizations[node_name] = NodeResourceUtilization()
            node_resources = self.node_resource_utilizations[node_name]
        return node_resources


@dataclass
class ResourceWindow:
    """
    资源采样窗口。

    记录某副本在时间窗口内的资源占用快照，供 MetricsServer 做窗口聚合。

    重要字段：
    - replica: replica 相关的内部状态或配置；本类方法会在对应业务阶段读取或更新它。
    - resources: 资源名称到资源占用值的映射。
    - time: 记录发生的时间戳，可以来自墙钟或仿真时钟。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    replica: FunctionReplica
    resources: Dict[str, float]
    time: float


class MetricsServer:
    """
    资源窗口指标服务。

    保存 ResourceWindow 并计算指定时间段内的平均资源利用率。

    重要字段：
    - _windows: 按节点和 Pod 组织的资源采样窗口。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self):
        """
        初始化 MetricsServer 对象。

        主要建立字段：_windows。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self._windows = defaultdict(lambda: defaultdict(list))

    def put(self, window: ResourceWindow):
        """
        保存一个资源采样窗口。

        窗口按节点名和 Pod 名两级索引，便于后续按副本查询一段时间内的资源利用率。

        参数说明：
        - window: window 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：ResourceWindow。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        node = window.replica.node.name
        pod = window.replica.pod.name

        # 二级索引让后续查询可以快速定位“某个节点上的某个 Pod”的历史窗口。
        self._windows[node][pod].append(window)

    def get_average_cpu_utilization(self, fn_replica: FunctionReplica, window_start: float, window_end: float) -> float:
        """
        计算指定副本在时间窗口内的平均 CPU 利用率。

        内部先取平均 CPU 使用量，再除以所在节点的 CPU 毫核容量，返回 0 到 1 附近的比例值。

        参数说明：
        - fn_replica: fn_replica 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：FunctionReplica。
        - window_start: 统计窗口开始时间。 类型标注：float。
        - window_end: 统计窗口结束时间。 类型标注：float。

        返回说明：返回值类型标注为 float，通常作为后续调度、执行、统计或查询流程的输入。
        """
        utilization = self.get_average_resource_utilization(fn_replica, 'cpu', window_start, window_end)
        millis = fn_replica.node.capacity.cpu_millis
        return utilization / millis

    def get_average_resource_utilization(self, fn_replica: FunctionReplica, resource: str, window_start: float,
                                         window_end: float) -> float:
        """
        计算指定资源在时间窗口内的平均占用。

        方法从最近采样窗口向前扫描，只使用 window_start 到 window_end 范围内的数据。

        参数说明：
        - fn_replica: fn_replica 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：FunctionReplica。
        - resource: 资源名，例如 cpu、memory、net 等。 类型标注：str。
        - window_start: 统计窗口开始时间。 类型标注：float。
        - window_end: 统计窗口结束时间。 类型标注：float。

        返回说明：返回值类型标注为 float，通常作为后续调度、执行、统计或查询流程的输入。
        """
        node = fn_replica.node.name
        pod = fn_replica.pod.name
        windows: List[ResourceWindow] = self._windows.get(node, {}).get(pod, [])
        if len(windows) == 0:
            return 0
        average_windows = []

        # 从最新窗口向前扫描，遇到早于 window_start 的采样即可停止。
        # 这样在窗口数量较多时不用每次遍历完整历史。
        for window in reversed(windows):
            if window.time <= window_end:
                if window.time < window_start:
                    break
                average_windows.append(window)
        
        return np.mean(list(map(lambda l: l.resources[resource], average_windows)))


class ResourceMonitor:
    """
    周期性资源监控进程。

    按照 reconcile_interval 读取资源状态，写入 MetricsServer 和 Metrics。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - reconcile_interval: 后台控制循环执行间隔。
    - metric_server: metric_server 相关的内部状态或配置；本类方法会在对应业务阶段读取或更新它。
    - logging: logging 相关的内部状态或配置；本类方法会在对应业务阶段读取或更新它。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self, env: Environment, reconcile_interval: int, logging=True):
        """
        初始化资源监控器。

        保存仿真环境、采样周期、MetricsServer 引用和是否写入 Metrics 的开关。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - reconcile_interval: 控制器重新计算决策的周期。 类型标注：int。
        - logging: logging 参数，参与当前方法的计算、查询、状态更新或流程控制。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env
        self.reconcile_interval = reconcile_interval
        self.metric_server: MetricsServer = env.metrics_server
        self.logging = logging

    def run(self):
        """
        周期性采样运行中副本的资源占用。

        每隔 reconcile_interval 遍历所有 RUNNING 副本，跳过空资源记录，将快照写入 MetricsServer，并在 logging 开启时同步写入 Metrics。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：run 方法通常是后台控制循环或实验主流程，阅读时要看循环内的 yield 与 env.process。
        """
        faas: FaasSystem = self.env.faas
        while True:
            yield self.env.timeout(self.reconcile_interval)
            now = self.env.now
            for deployment in faas.get_deployments():
                for replica in faas.get_replicas(deployment.name, FunctionState.RUNNING):
                    # ResourceMonitor 只采样 RUNNING 副本；未启动或已挂起副本不会进入资源窗口。
                    utilization = self.env.resource_state.get_resource_utilization(replica)
                    if utilization.is_empty():
                        continue
                    if self.logging:
                        self.env.metrics.log_function_resource_utilization(replica, utilization)
                    # MetricsServer 保存窗口快照，HPA 后续会按时间窗口计算平均 CPU 利用率。
                    self.metric_server.put(
                        ResourceWindow(replica, utilization.list_resources(), now))
