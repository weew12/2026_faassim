"""
性能、成本与资源 Oracle。

Oracle 负责根据调度上下文、Pod 和调度结果估计某类指标。经验型 Oracle 从 CSV 数据中采样，拟合型 Oracle 从预定义分布采样，统一返回指标名和值。

阅读建议：把 Oracle 理解为调度或执行过程中的估计器，经验型读 CSV，拟合型读分布。
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

Bandwidth = NamedTuple('Bandwidth', [('mbit', int), ('delay', int), ('deviation', int)])

data_dir = 'sim/oracle/data'


class Oracle:
    """
    估计器接口。

    根据调度上下文、Pod 和调度结果返回某类指标名和值。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
        """
        raise NotImplementedError


class EmpiricalOracle:
    """
    经验数据 Oracle 基类。

    加载 CSV 观测数据并进行基本清洗，供启动时间和执行时间 Oracle 采样。

    重要字段：
    - dataset: 从 CSV 加载并清洗后的经验观测数据。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self, filename):
        """
        初始化 EmpiricalOracle 对象。

        主要建立字段：dataset。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - filename: 经验数据 CSV 文件路径或通配符。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        csvs = glob.glob(filename)
        dfs = [pd.read_csv(filename) for filename in csvs]
        df = pd.concat(dfs)
        
        df = df.loc[df['status'].isin(['passed'])]
        
        df['bandwidth'] = df['bandwidth'].apply(lambda x: eval(x))
        
        df['bandwidth'] = df['bandwidth'].apply(lambda x: 1.25e+8 if x is None else parse_size_string(f'{x.mbit}M') / 8)
        
        df['host'] = df['host'].apply(lambda x: make_tuple(x)[0][:-1])
        self.dataset = df


class StartupTimeOracle(EmpiricalOracle):
    """
    经验启动时间 Oracle。

    根据主机类型、镜像、带宽和镜像是否已缓存，从历史数据中采样启动耗时。

    重要字段：
    - durations: Oracle 使用的耗时采样表。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self):
        """
        初始化 StartupTimeOracle 对象。

        主要建立字段：durations。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super(StartupTimeOracle, self).__init__(os.path.join(data_dir, 'pod_startup_*.csv'))
        self.durations = self.dataset[['host', 'bandwidth', 'image', 'image_present', 'duration']]

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
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
    经验执行时间 Oracle。

    根据主机类型、镜像和带宽，从历史数据中采样执行耗时。

    重要字段：
    - durations: Oracle 使用的耗时采样表。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self):
        """
        初始化 ExecutionTimeOracle 对象。

        主要建立字段：durations。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super(ExecutionTimeOracle, self).__init__(os.path.join(data_dir, 'exec_time*.csv'))
        self.durations = self.dataset[['host', 'bandwidth', 'image', 'duration']]

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'execution_time', None
        host = scheduling_result.suggested_host.name
        host_type = host[host.rindex('_') + 1:]
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
    带宽使用量 Oracle。

    估计调度某个 Pod 需要传输的镜像和输入/输出数据量。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'bandwidth_usage', None

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
    成本 Oracle。

    基于执行时间和节点类型估计云端运行成本。

    重要字段：
    - execution_time_oracle: 用于估计执行时间的 Oracle，成本 Oracle 会复用它计算费用。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    execution_time_oracle: Oracle

    def __init__(self, execution_time_oracle=None) -> None:
        """
        初始化 CostOracle 对象。

        主要建立字段：execution_time_oracle。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - execution_time_oracle: 执行时间 Oracle，用于成本估计或组合估计。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.execution_time_oracle = execution_time_oracle or FittedExecutionTimeOracle()

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'cost', None
        cost = 0
        labels = scheduling_result.suggested_host.labels
        if 'locality.skippy.io/type' in labels and labels['locality.skippy.io/type'] == 'cloud':
            _, time_str = self.execution_time_oracle.estimate(context, pod, scheduling_result)
            
            
            cost = 0.000001667 * 10 * float(time_str)
        return 'cost', str(cost)


class ResourceUtilizationOracle(Oracle):
    """
    资源利用率 Oracle。

    根据 Pod 请求和节点容量估计资源使用分数，用于调度评分。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
        """
        if scheduling_result is None or scheduling_result.suggested_host is None:
            return 'resource_utilization', None
        resource_utilization = 0
        node = scheduling_result.suggested_host
        labels = scheduling_result.suggested_host.labels
        if 'locality.skippy.io/type' in labels and labels['locality.skippy.io/type'] == 'edge':
            resource_utilization = self.score_resource_utilization(pod, node)
        return 'resource_utilization', str(resource_utilization)

    def score_resource_utilization(self, pod, node) -> float:
        """
        Oracle 估计/采样入口：score_resource_utilization。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - pod: Skippy Pod，表示待调度的工作负载。
        - node: 目标节点或节点视图。

        返回说明：返回值类型标注为 float，通常作为后续调度、执行、统计或查询流程的输入。
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
    拟合启动时间 Oracle。

    从预定义分布采样启动耗时，避免依赖完整原始观测数据。

    重要字段：
    - startup_time_samplers: 启动时间分布采样器索引。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self) -> None:
        """
        初始化 FittedStartupTimeOracle 对象。

        主要建立字段：startup_time_samplers。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.startup_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            startup_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
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
    带修正逻辑的拟合启动时间 Oracle。

    在基础拟合采样上加入特殊场景处理，用于兼容历史实验数据。

    重要字段：
    - startup_time_samplers: 启动时间分布采样器索引。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    def __init__(self) -> None:
        """
        初始化 HackedFittedStartupTimeOracle 对象。

        主要建立字段：startup_time_samplers。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.startup_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            startup_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
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
        读取 sampler 相关状态。

        该方法不推进仿真时间，只根据当前索引、缓存或对象字段返回结果。调用方需要处理返回 None 或空列表的情况。

        参数说明：
        - host_type: 节点硬件类型字符串。
        - image: 镜像名或 FunctionImage。
        - image_present: 目标节点是否已经缓存该镜像。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        image_key = image.split(':')[0]  

        k = (host_type, image_key, image_present)
        if k not in self.startup_time_samplers:
            raise ValueError(k)

        return self.startup_time_samplers[k]


class FittedExecutionTimeOracle(Oracle):

    """
    拟合执行时间 Oracle。

    根据主机类型和镜像从分布采样函数执行时间。

    重要字段：
    - execution_time_samplers: 执行时间分布采样器索引。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def __init__(self) -> None:
        """
        初始化 FittedExecutionTimeOracle 对象。

        主要建立字段：execution_time_samplers。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        super().__init__()
        self.execution_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            execution_time_distributions.items()
        }

    def estimate(self, context: ClusterContext, pod: Pod, scheduling_result: SchedulingResult) -> Tuple[str, str]:
        """
        Oracle 估计/采样入口：estimate。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - context: Skippy 调度上下文。 类型标注：ClusterContext。
        - pod: Skippy Pod，表示待调度的工作负载。 类型标注：Pod。
        - scheduling_result: 调度器返回的结果，包含 suggested_host 和所需镜像等信息。 类型标注：SchedulingResult。

        返回说明：返回值类型标注为 Tuple[str, str]，通常作为后续调度、执行、统计或查询流程的输入。

        业务流程：Oracle 的 estimate 只计算指标值，不直接改变仿真时间；调用方决定如何使用估计结果。
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
        读取 sampler 相关状态。

        该方法不推进仿真时间，只根据当前索引、缓存或对象字段返回结果。调用方需要处理返回 None 或空列表的情况。

        参数说明：
        - host_type: 节点硬件类型字符串。
        - image: 镜像名或 FunctionImage。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        image_key = image.split(':')[0]  

        k = (host_type, image_key)
        if k not in self.execution_time_samplers:
            raise ValueError(k)

        return self.execution_time_samplers[k]


class FetOracle:

    """
    函数执行时间查询接口。

    按 host 和 image 返回函数执行时间样本。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def sample(self, host: str, image: str) -> Optional[float]:
        """
        Oracle 估计/采样入口：sample。

        根据调度上下文、节点、镜像或资源画像返回估计值。该类方法通常服务于调度评分、生命周期耗时或性能退化计算。

        参数说明：
        - host: 主机或节点名称。 类型标注：str。
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        raise NotImplementedError()


class ResourceOracle:

    """
    函数资源画像查询接口。

    按 host 和 image 返回 FunctionResourceCharacterization。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """
    def get_resources(self, host: str, image: str) -> 'FunctionResourceCharacterization':
        """
        读取 resources 相关状态。

        该方法不推进仿真时间，只根据当前索引、缓存或对象字段返回结果。调用方需要处理返回 None 或空列表的情况。

        参数说明：
        - host: 主机或节点名称。 类型标注：str。
        - image: 镜像名或 FunctionImage。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        raise NotImplementedError()
