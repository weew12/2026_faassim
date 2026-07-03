"""
文件作用：资源状态和资源监控实现，记录函数副本在节点上的 CPU、内存、网络、磁盘等资源占用，并按窗口汇总指标。
主要类：ResourceUtilization、NodeResourceUtilization、ResourceState、ResourceWindow、MetricsServer、ResourceMonitor。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
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
    类作用：单个副本或对象的资源集合，支持资源添加、移除、复制和按名称读取。
    核心字段：__resources：内部资源字典，按资源名保存资源占用值。。
    核心方法：__init__、put_resource、remove_resource、list_resources、copy、get_resource、is_empty。
    """
    # 字段说明：__resources：内部资源字典，按资源名保存资源占用值。
    __resources: Dict[str, float]

    def __init__(self):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：__resources。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.__resources：内部资源字典，按资源名保存资源占用值。
        self.__resources = {}

    def put_resource(self, resource: str, value: float):
        """
        函数作用：给指定资源名登记一个资源占用值。
        参数：resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if self.__resources.get(resource) is None:
            self.__resources[resource] = 0
        self.__resources[resource] += value

    def remove_resource(self, resource: str, value: float):
        """
        函数作用：移除指定资源占用。
        参数：resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if self.__resources.get(resource) is None:
            self.__resources[resource] = 0
        self.__resources[resource] -= value

    def list_resources(self) -> Dict[str, float]:
        """
        函数作用：列出当前对象持有的资源名。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return deepcopy(self.__resources)

    def copy(self) -> 'ResourceUtilization':
        """
        函数作用：复制当前对象，避免外部修改影响原状态。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        util = ResourceUtilization()
        util.__resources = self.list_resources()
        return util

    def get_resource(self, resource) -> Optional[float]:
        """
        函数作用：读取指定资源名对应的占用值。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：resource：资源名称或资源对象。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.__resources.get(resource)

    def is_empty(self) -> bool:
        """
        函数作用：判断当前资源集合是否为空。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return len(self.__resources) == 0


class NodeResourceUtilization:
    # 业务说明：这里处理节点、拓扑或网络连接相关状态。
    """
    类作用：节点级资源使用视图，按副本聚合资源并计算节点总利用率。
    核心字段：__resources：内部资源字典，按资源名保存资源占用值。；__replicas：内部副本字典，按副本对象保存其资源使用情况。。
    核心方法：__init__、put_resource、remove_resource、get_resource_utilization、list_resource_utilization、total_utilization。
    """
    # 字段说明：__resources：内部资源字典，按资源名保存资源占用值。
    __resources: Dict[str, ResourceUtilization]

    
    # 字段说明：__replicas：内部副本字典，按副本对象保存其资源使用情况。
    __replicas: Dict[str, FunctionReplica]

    def __init__(self):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：__replicas、__resources。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.__resources：内部资源字典，按资源名保存资源占用值。
        self.__resources = {}
        # 字段说明：self.__replicas：内部副本字典，按副本对象保存其资源使用情况。
        self.__replicas = {}

    def put_resource(self, replica: FunctionReplica, resource: str, value: float):
        """
        函数作用：给指定资源名登记一个资源占用值。
        关键流程：
        - 向资源状态登记占用，反映函数副本在节点上的运行负载。
        参数：replica：正在部署、执行或释放的函数副本。；resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 资源占用：登记函数当前阶段占用的资源。
        self.get_resource_utilization(replica).put_resource(resource, value)

    def remove_resource(self, replica: FunctionReplica, resource: str, value: float):
        """
        函数作用：移除指定资源占用。
        关键流程：
        - 从资源状态移除占用，避免已结束阶段继续影响资源利用率。
        参数：replica：正在部署、执行或释放的函数副本。；resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        self.get_resource_utilization(replica).remove_resource(resource, value)

    def get_resource_utilization(self, replica: FunctionReplica) -> ResourceUtilization:
        """
        函数作用：读取某副本或某节点的资源利用率对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：与该业务步骤对应的对象、指标或计算结果。
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
        函数作用：列出节点上所有副本的资源利用率。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        functions = []
        for pod_name, utilization in self.__resources.items():
            replica = self.__replicas.get(pod_name)
            functions.append((replica, utilization))
        return functions

    @property
    def total_utilization(self) -> ResourceUtilization:
        """
        函数作用：汇总节点上所有副本的资源占用。
        关键流程：
        - 向资源状态登记占用，反映函数副本在节点上的运行负载。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        total = ResourceUtilization()
        for _, resource_utilization in self.list_resource_utilization():
            for resource, value in resource_utilization.list_resources().items():
                # 资源占用：登记函数当前阶段占用的资源。
                total.put_resource(resource, value)
        return total


class ResourceState:
    """
    类作用：全局资源状态表，按节点维护 NodeResourceUtilization。
    核心字段：node_resource_utilizations：按节点索引的资源利用率表。。
    核心方法：__init__、put_resource、remove_resource、get_resource_utilization、list_resource_utilization、get_node_resource_utilization。
    """
    # 字段说明：node_resource_utilizations：按节点索引的资源利用率表。
    node_resource_utilizations: Dict[str, NodeResourceUtilization]

    def __init__(self):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：node_resource_utilizations。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.node_resource_utilizations：按节点索引的资源利用率表。
        self.node_resource_utilizations = {}

    def put_resource(self, function_replica: FunctionReplica, resource: str, value: float):
        """
        函数作用：给指定资源名登记一个资源占用值。
        关键流程：
        - 向资源状态登记占用，反映函数副本在节点上的运行负载。
        参数：function_replica：表示 function、replica，在当前业务流程中作为输入参数、状态字段或计算结果使用。；resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        node_name = function_replica.node.name
        node_resources = self.get_node_resource_utilization(node_name)
        # 资源占用：登记函数当前阶段占用的资源。
        node_resources.put_resource(function_replica, resource, value)

    def remove_resource(self, replica: 'FunctionReplica', resource: str, value: float):
        """
        函数作用：移除指定资源占用。
        关键流程：
        - 从资源状态移除占用，避免已结束阶段继续影响资源利用率。
        参数：replica：正在部署、执行或释放的函数副本。；resource：资源名称或资源对象。；value：写入资源表或配置表的具体数值。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        node_name = replica.node.name
        # 资源释放：移除函数当前阶段占用，避免影响后续资源统计。
        self.get_node_resource_utilization(node_name).remove_resource(replica, resource, value)

    def get_resource_utilization(self, replica: 'FunctionReplica') -> 'ResourceUtilization':
        """
        函数作用：读取某副本或某节点的资源利用率对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：replica：正在部署、执行或释放的函数副本。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        node_name = replica.node.name
        return self.get_node_resource_utilization(node_name).get_resource_utilization(replica)

    def list_resource_utilization(self, node_name: str) -> List[Tuple['FunctionReplica', 'ResourceUtilization']]:
        """
        函数作用：列出节点上所有副本的资源利用率。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.get_node_resource_utilization(node_name).list_resource_utilization()

    def get_node_resource_utilization(self, node_name: str) -> Optional[NodeResourceUtilization]:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        node_resources = self.node_resource_utilizations.get(node_name)
        if node_resources is None:
            self.node_resource_utilizations[node_name] = NodeResourceUtilization()
            node_resources = self.node_resource_utilizations[node_name]
        return node_resources


@dataclass
class ResourceWindow:
    """
    类作用：资源监控窗口记录，保存某一时刻某副本的资源快照。
    核心字段：replica：函数副本对象。；resources：资源集合，表示 CPU、内存、网络、磁盘或 GPU 等占用。；time：记录产生的时间戳。。
    """
    # 字段说明：replica：函数副本对象。
    replica: FunctionReplica
    # 字段说明：resources：资源集合，表示 CPU、内存、网络、磁盘或 GPU 等占用。
    resources: Dict[str, float]
    # 字段说明：time：记录产生的时间戳。
    time: float


class MetricsServer:
    """
    类作用：简化版指标服务器，缓存资源窗口并计算窗口内平均 CPU/资源利用率。
    核心方法：__init__、put、get_average_cpu_utilization、get_average_resource_utilization。
    """

    def __init__(self):
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：_windows。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self._windows：表示 windows，在当前业务流程中作为输入参数、状态字段或计算结果使用。
        self._windows = defaultdict(lambda: defaultdict(list))

    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    def put(self, window: ResourceWindow):
        """
        函数作用：向内部索引或仓库写入一个对象。
        参数：window：表示 window，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        node = window.replica.node.name
        pod = window.replica.pod.name

        self._windows[node][pod].append(window)

    def get_average_cpu_utilization(self, fn_replica: FunctionReplica, window_start: float, window_end: float) -> float:
        """
        函数作用：按时间窗口计算函数副本的平均 CPU 利用率。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_replica：表示 fn、replica，在当前业务流程中作为输入参数、状态字段或计算结果使用。；window_start：表示 window、start，在当前业务流程中作为输入参数、状态字段或计算结果使用。；window_end：表示 window、end，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        utilization = self.get_average_resource_utilization(fn_replica, 'cpu', window_start, window_end)
        millis = fn_replica.node.capacity.cpu_millis
        return utilization / millis

    def get_average_resource_utilization(self, fn_replica: FunctionReplica, resource: str, window_start: float,
                                         window_end: float) -> float:
        """
        函数作用：按时间窗口计算指定资源的平均利用率。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_replica：表示 fn、replica，在当前业务流程中作为输入参数、状态字段或计算结果使用。；resource：资源名称或资源对象。；window_start：表示 window、start，在当前业务流程中作为输入参数、状态字段或计算结果使用。；window_end：表示 window、end，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        node = fn_replica.node.name
        pod = fn_replica.pod.name
        windows: List[ResourceWindow] = self._windows.get(node, {}).get(pod, [])
        if len(windows) == 0:
            return 0
        average_windows = []

        for window in reversed(windows):
            if window.time <= window_end:
                if window.time < window_start:
                    break
                average_windows.append(window)
        
        return np.mean(list(map(lambda l: l.resources[resource], average_windows)))


class ResourceMonitor:
    """
    类作用：资源监控后台进程，周期采样资源状态并写入 MetricsServer 与 Metrics。
    核心方法：__init__、run。
    """

    def __init__(self, env: Environment, reconcile_interval: int, logging=True):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：env、logging、metric_server、reconcile_interval。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。；logging：表示 logging，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.reconcile_interval：后台控制循环的重调谐间隔，决定伸缩器或监控器多久执行一次判断。
        self.reconcile_interval = reconcile_interval
        # 字段说明：self.metric_server：资源指标服务器，缓存监控窗口并提供平均资源利用率查询。
        self.metric_server: MetricsServer = env.metrics_server
        # 字段说明：self.logging：表示 logging，在当前业务流程中作为输入参数、状态字段或计算结果使用。
        self.logging = logging

    def run(self):
        """
        函数作用：启动实验或后台进程的主循环，在仿真时间内持续推进业务行为。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        faas: FaasSystem = self.env.faas
        while True:
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield self.env.timeout(self.reconcile_interval)
            now = self.env.now
            for deployment in faas.get_deployments():
                for replica in faas.get_replicas(deployment.name, FunctionState.RUNNING):
                    utilization = self.env.resource_state.get_resource_utilization(replica)
                    if utilization.is_empty():
                        continue
                    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
                    if self.logging:
                        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
                        self.env.metrics.log_function_resource_utilization(replica, utilization)
                    self.metric_server.put(
                        ResourceWindow(replica, utilization.list_resources(), now))
