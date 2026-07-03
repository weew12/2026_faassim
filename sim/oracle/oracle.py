"""
文件作用：性能与资源 Oracle 抽象集合，封装启动时间、执行时间、带宽、成本、资源利用率和拟合分布采样等估计接口。
主要类：Oracle、EmpiricalOracle、StartupTimeOracle、ExecutionTimeOracle、BandwidthUsageOracle、CostOracle、ResourceUtilizationOracle、FittedStartupTimeOracle、HackedFittedStartupTimeOracle、FittedExecutionTimeOracle、FetOracle、ResourceOracle。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import glob
import os
from ast import literal_eval as make_tuple
from typing import NamedTuple
from typing import Tuple, Optional

import pandas as pd
from skippy.core.clustercontext import ClusterContext
from skippy.core.model import Pod, SchedulingResult, ImageState
from skippy.core.utils import parse_size_string, normalize_image_name
from srds import BoundRejectionSampler, BufferedSampler

from sim.oracle.data.distributions import execution_time_distributions, startup_time_distributions

# 字段说明：Bandwidth：表示 bandwidth，在当前业务流程中作为输入参数、状态字段或计算结果使用。
Bandwidth = NamedTuple('Bandwidth', [('mbit', int), ('delay', int), ('deviation', int)])

# 字段说明：data_dir：表示 data、dir，在当前业务流程中作为输入参数、状态字段或计算结果使用。
data_dir = 'sim/oracle/data'


class Oracle:
    """
    类作用：估计器抽象接口，定义根据上下文估计某类性能或资源指标的统一方法。
    核心方法：estimate。
    """

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError


class EmpiricalOracle:
    """
    类作用：经验型 Oracle 基类，保存实验观测数据供子类估计使用。
    核心方法：__init__。
    """
    def __init__(self, filename):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：dataset。
        - 整理为表格数据，服务于后续实验分析。
        参数：filename：表示 filename，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        csvs = glob.glob(filename)
        dfs = [pd.read_csv(filename) for filename in csvs]
        df = pd.concat(dfs)
        
        df = df.loc[df['status'].isin(['passed'])]
        
        df['bandwidth'] = df['bandwidth'].apply(lambda x: eval(x))
        
        df['bandwidth'] = df['bandwidth'].apply(lambda x: 1.25e+8 if x is None else parse_size_string(f'{x.mbit}M') / 8)
        
        df['host'] = df['host'].apply(lambda x: make_tuple(x)[0][:-1])
        # 字段说明：self.dataset：画像或实验数据集，用于构造 Oracle、统计表或训练输入。
        self.dataset = df


class StartupTimeOracle(EmpiricalOracle):
    """
    类作用：启动时间 Oracle，估计函数副本从创建到可运行的耗时。
    继承关系：EmpiricalOracle。
    核心方法：__init__、estimate。
    """
    def __init__(self):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：durations。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super(StartupTimeOracle, self).__init__(os.path.join(data_dir, 'pod_startup_*.csv'))
        # 字段说明：self.durations：历史耗时样本集合，用于经验分布采样。
        self.durations = self.dataset[['host', 'bandwidth', 'image', 'image_present', 'duration']]

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'startup_time', None
        host = scheduling_result.suggested_host.name
        host_type = host[host.rindex('_') + 1:]
        
        bandwidth = context.get_bandwidth_graph()[host]['registry']
        startup_time = 0

        for container in pod.spec.containers:
            image = container.image
            image_present = normalize_image_name(image) not in scheduling_result.needed_images

            data = self.durations.query(f'host == "{host_type}" and '
                                        f'image == "{image}" and '
                                        f'bandwidth == "{bandwidth}" and '
                                        f'image_present == {image_present}')

            if data.empty:
                raise ValueError('no data for %s, %s, %s, %s' % (host_type, image, bandwidth, image_present))
            else:
                sample = data['duration'].sample()

            startup_time += sample.values[0]

        return 'startup_time', str(startup_time)


class ExecutionTimeOracle(EmpiricalOracle):
    """
    类作用：执行时间 Oracle，估计函数请求在指定节点上的执行时长。
    继承关系：EmpiricalOracle。
    核心方法：__init__、estimate。
    """
    def __init__(self):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：durations。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super(ExecutionTimeOracle, self).__init__(os.path.join(data_dir, 'exec_time*.csv'))
        # 字段说明：self.durations：历史耗时样本集合，用于经验分布采样。
        self.durations = self.dataset[['host', 'bandwidth', 'image', 'duration']]

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'execution_time', None
        host = scheduling_result.suggested_host.name
        host_type = host[host.rindex('_') + 1:]
        # 业务说明：这里处理节点、拓扑或网络连接相关状态。
        bandwidth = context.get_bandwidth_graph()[host][context.get_next_storage_node(scheduling_result.suggested_host)]
        execution_time = 0
        for container in pod.spec.containers:
            image = container.image
            execution_time += self.durations.query(f'host == "{host_type}" and '
                                                   f'bandwidth == {bandwidth} and '
                                                   f'image == "{image}"')['duration'].sample().values[0]
        return 'execution_time', str(execution_time)


class BandwidthUsageOracle(Oracle):
    """
    类作用：BandwidthUsageOracle 类，封装 bandwidth、usage、oracle 相关状态和业务操作。
    继承关系：Oracle。
    核心方法：estimate。
    """
    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'bandwidth_usage', None

        # 业务说明：这里处理镜像或数据下载，相关耗时会进入仿真时间。
        bandwidth_usage = 0
        node = scheduling_result.suggested_host
        for image_name in scheduling_result.needed_images:
            try:
                image_state: ImageState = context.images_on_nodes[node.name][image_name]
                bandwidth_usage += image_state.size[node.labels['beta.kubernetes.io/arch']]
            except KeyError:
                pass

        
        bandwidth_usage += parse_size_string(pod.spec.labels.get('data.skippy.io/receives-from-storage', '0'))
        bandwidth_usage += parse_size_string(pod.spec.labels.get('data.skippy.io/sends-to-storage', '0'))

        return 'bandwidth_usage', str(bandwidth_usage)


class CostOracle(Oracle):
    """
    类作用：成本 Oracle，根据执行时间和资源价格估计函数调用成本。
    继承关系：Oracle。
    核心字段：execution_time_oracle：执行时间估计器，供成本或调度评分复用。。
    核心方法：__init__、estimate。
    """
    # 字段说明：execution_time_oracle：执行时间估计器，供成本或调度评分复用。
    execution_time_oracle: Oracle

    def __init__(self, execution_time_oracle=None) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：execution_time_oracle。
        参数：execution_time_oracle：执行时间估计器，供成本或调度评分复用。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.execution_time_oracle：执行时间估计器，供成本或调度评分复用。
        self.execution_time_oracle = execution_time_oracle or FittedExecutionTimeOracle()

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'cost', None
        cost = 0
        labels = scheduling_result.suggested_host.labels
        if 'locality.skippy.io/type' in labels and labels['locality.skippy.io/type'] == 'cloud':
            _, time_str = self.execution_time_oracle.estimate(context, pod, scheduling_result)
            # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
            
            
            cost = 0.000001667 * 10 * float(time_str)
        return 'cost', str(cost)


class ResourceUtilizationOracle(Oracle):
    """
    类作用：资源利用率 Oracle，估计或评分函数执行对节点资源的占用。
    继承关系：Oracle。
    核心方法：estimate、score_resource_utilization。
    """
    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'resource_utilization', None
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
        resource_utilization = 0
        node = scheduling_result.suggested_host
        labels = scheduling_result.suggested_host.labels
        if 'locality.skippy.io/type' in labels and labels['locality.skippy.io/type'] == 'edge':
            resource_utilization = self.score_resource_utilization(pod, node)
        return 'resource_utilization', str(resource_utilization)

    def score_resource_utilization(self, pod, node) -> float:
        """
        函数作用：处理 score、resource、utilization 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：pod：调度器使用的 Pod 视图。；node：候选或目标节点。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        mem_cap = node.capacity.memory
        cpu_cap = node.capacity.cpu_millis
        mem_all = 0
        cpu_all = 0
        for container in pod.spec.containers:
            cpu_all += container.resources.requests.get('cpu', container.resources.default_milli_cpu_request)
            mem_all += container.resources.requests.get('memory', container.resources.default_mem_request)
        return (mem_all / mem_cap) + (cpu_all / cpu_cap)


class FittedStartupTimeOracle(Oracle):

    """
    类作用：FittedStartupTimeOracle 类，封装 fitted、startup、time、oracle 相关状态和业务操作。
    继承关系：Oracle。
    核心方法：__init__、estimate。
    """
    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：startup_time_samplers。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.startup_time_samplers：按节点或函数索引的启动时间采样器集合。
        self.startup_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            startup_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'startup_time', None

        host = scheduling_result.suggested_host.name
        host_type = host[host.rindex('_') + 1:]
        
        bandwidth = context.get_bandwidth_graph()[host]['registry']
        startup_time = 0

        for container in pod.spec.containers:
            image = container.image

            image_present = normalize_image_name(image) not in scheduling_result.needed_images

            k = (host_type, image, image_present, bandwidth)

            if k not in self.startup_time_samplers:
                raise ValueError(k)

            startup_time += self.startup_time_samplers[k].sample()

        return 'startup_time', str(startup_time)


class HackedFittedStartupTimeOracle(Oracle):
    """
    类作用：HackedFittedStartupTimeOracle 类，封装 hacked、fitted、startup、time、oracle 相关状态和业务操作。
    继承关系：Oracle。
    核心方法：__init__、estimate、get_sampler。
    """

    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：startup_time_samplers。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.startup_time_samplers：按节点或函数索引的启动时间采样器集合。
        self.startup_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            startup_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'startup_time', None

        host = scheduling_result.suggested_host.name
        host_arch = scheduling_result.suggested_host.labels['beta.kubernetes.io/arch']
        host_type = host[host.rindex('_') + 1:]
        bandwidth = int(1.25e7)  
        startup_time = 0

        for container in pod.spec.containers:
            image = container.image
            image_name = normalize_image_name(image)

            image_present = image_name not in scheduling_result.needed_images

            image_time = self.get_sampler(host_type, image, image_present).sample()

            if not image_present:
                image_size = context.get_image_state(image_name).size[host_arch]
                dl_time = image_size / bandwidth
                image_time = max(0, image_time - dl_time)

            startup_time += image_time

        return 'startup_time', str(startup_time)

    def get_sampler(self, host_type, image, image_present):
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host_type：表示 host、type，在当前业务流程中作为输入参数、状态字段或计算结果使用。；image：容器镜像标识。；image_present：表示 image、present，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        image_key = image.split(':')[0]  

        k = (host_type, image_key, image_present)
        if k not in self.startup_time_samplers:
            raise ValueError(k)

        return self.startup_time_samplers[k]


class FittedExecutionTimeOracle(Oracle):

    """
    类作用：FittedExecutionTimeOracle 类，封装 fitted、execution、time、oracle 相关状态和业务操作。
    继承关系：Oracle。
    核心方法：__init__、estimate、get_sampler。
    """
    def __init__(self) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：execution_time_samplers。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.execution_time_samplers：按节点或函数索引的执行时间采样器集合。
        self.execution_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            execution_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        函数作用：根据上下文估计性能、资源或成本指标。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：context：估计器所需上下文。；pod：调度器使用的 Pod 视图。；scheduling_result：调度器输出结果，包含候选节点选择、可行性和调度评分信息。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'execution_time', None

        host = scheduling_result.suggested_host.name
        host_type = host[:host.rindex('_')]

        execution_time = 0
        for container in pod.spec.containers:
            image = container.image

            
            execution_time += self.get_sampler(host_type, image).sample()

        return 'execution_time', str(execution_time)

    def get_sampler(self, host_type, image):
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host_type：表示 host、type，在当前业务流程中作为输入参数、状态字段或计算结果使用。；image：容器镜像标识。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        image_key = image.split(':')[0]  

        k = (host_type, image_key)
        if k not in self.execution_time_samplers:
            raise ValueError(k)

        return self.execution_time_samplers[k]


class FetOracle:

    """
    类作用：函数执行时间采样接口，供 FunctionCharacterization 在节点上采样 FET。
    核心方法：sample。
    """
    def sample(self, host: str, image: str) -> Optional[float]:
        """
        函数作用：从经验分布或画像数据中采样一个函数执行时间。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：host：执行函数的目标主机或节点。；image：容器镜像标识。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError()


class ResourceOracle:

    """
    类作用：资源向量查询接口，供 FunctionCharacterization 获取节点相关资源画像。
    核心方法：get_resources。
    """
    def get_resources(self, host: str, image: str) -> 'FunctionResourceCharacterization':
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：host：执行函数的目标主机或节点。；image：容器镜像标识。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        raise NotImplementedError()
