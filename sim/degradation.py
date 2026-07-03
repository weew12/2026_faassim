"""
文件作用：性能退化模型输入构造文件，将当前并发函数的资源向量汇总成固定长度特征，供机器学习退化模型预测使用。
主要函数：create_degradation_model_input。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import logging
from collections import defaultdict
from typing import List

import numpy as np

from .oracle.oracle import ResourceOracle


def create_degradation_model_input(calls: List, start_ts, end_ts, node_name: str,
                                   ram_capacity: float,
                                   resource_oracle: ResourceOracle) -> np.ndarray:
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    
    
    
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    
    
    
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    
    
    
    
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：calls：表示 calls，在当前业务流程中作为输入参数、状态字段或计算结果使用。；start_ts：表示 start、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。；end_ts：表示 end、ts，在当前业务流程中作为输入参数、状态字段或计算结果使用。；node_name：节点名称，用于在拓扑、资源状态或调度结果中定位具体节点。；ram_capacity：表示 ram、capacity，在当前业务流程中作为输入参数、状态字段或计算结果使用。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    resources_types = ['cpu', 'gpu', 'blkio', 'net']

    if len(calls) == 0:
        return np.array([])
    ram = 0
    seen_pods = set()
    resources = defaultdict(lambda: defaultdict(list))
    for call in calls:
        function = call.replica.function
        pod_name = call.replica.pod.name
        call_resources = resource_oracle.get_resources(node_name, function)
        if call_resources:
            raise ValueError(f"Can't find resources for node '{node_name}' for function {function}")
        for resource_type in resources_types:
            resources[pod_name][resource_type].append(call_resources[resource_type])
        if len(call_resources) == 0:
            logging.debug(f'Function {function.name} has no resources for node {node_name}')
            continue

        if pod_name not in seen_pods:
            ram += call.replica.pod.spec.containers[0].resources.requests['memory']
            seen_pods.add(pod_name)
        last_start = start_ts if start_ts >= call.start else call.start

        if call.end is not None:
            first_end = end_ts if end_ts <= call.end else call.end
        else:
            first_end = end_ts

        overlap = first_end - last_start

        for resource in resources_types:
            resources[pod_name][resource].append(overlap * call_resources[resource])

    sums = defaultdict(list)
    for resource_type in resources_types:
        for pod_name, resources_of_pod in resources.items():
            resource_sum = np.sum(resources_of_pod[resource_type])
            sums[resource_type].append(resource_sum)

    
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    
    input = []
    for resource in resources_types:
        mean = np.mean(sums[resource])
        std = np.std(sums[resource])
        amin = np.min(sums[resource])
        amax = np.max(sums[resource])
        p_25 = np.percentile(sums[resource], q=0.25)
        p_50 = np.percentile(sums[resource], q=0.5)
        p_75 = np.percentile(sums[resource], q=0.75)
        for value in [mean, std, amin, amax, p_25, p_50, p_75]:
            
            if np.isnan(value):
                input.append(0)
            else:
                input.append(value)

    
    input.append(len(sums['cpu']))

    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    for resource in resources_types:
        input.append(np.sum(sums[resource]))

    
    input.append(ram / ram_capacity)

    return np.array(input)
