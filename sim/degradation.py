"""
性能退化模型输入构造。

本模块把某个时间窗口内并发函数调用的资源占用整理成固定顺序的数值特征，供节点级回归模型预测执行时间放大倍数。
它不负责训练模型，只负责从当前仿真状态和 ResourceOracle 中构造模型输入。
"""

import logging
from collections import defaultdict
from typing import List

import numpy as np

from .oracle.oracle import ResourceOracle


def create_degradation_model_input(calls: List, start_ts, end_ts, node_name: str,
                                   ram_capacity: float,
                                   resource_oracle: ResourceOracle) -> np.ndarray:
    
    
    
    
    
    
    
    
    
    
    
    
    
    """
    构造性能退化模型输入特征。

    方法根据时间窗口内并发调用、节点资源和资源 Oracle 生成特征向量，供 NodeState.estimate_degradation 调用模型预测。

    参数说明：
    - calls: 时间窗口内可能并发的历史请求列表。 类型标注：List。
    - start_ts: 统计或估计窗口的开始仿真时间。
    - end_ts: 统计或估计窗口的结束仿真时间。
    - node_name: 节点名称。 类型标注：str。
    - ram_capacity: 目标节点总内存容量，用于把内存占用转成相对特征。 类型标注：float。
    - resource_oracle: 资源 Oracle，用于查询函数在不同节点上的资源画像。 类型标注：ResourceOracle。

    返回说明：返回值类型标注为 np.ndarray，通常作为后续调度、执行、统计或查询流程的输入。
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

    for resource in resources_types:
        input.append(np.sum(sums[resource]))

    
    input.append(ram / ram_capacity)

    return np.array(input)
