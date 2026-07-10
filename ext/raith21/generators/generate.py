"""
设备生成结果导出工具。

本模块批量生成异构设备，统计设备类型和属性分布，并输出适合检查与实验记录的 CSV 结构。
"""

import os
import pickle
from collections import Counter, defaultdict
from typing import List, Dict

import pandas as pd
from ether.core import Node

from ..calculations import calculate_heterogeneity, calculate_requirements
from ..etherdevices import convert_to_devices, convert_to_ether_nodes
from ..generator import generate_devices, xeon_reqs
from ..generators.cloudcpu import cloudcpu_settings
from ..generators.cloudgpu import cloudgpu_settings
from ..generators.edgecloudlet import edgecloudlet_settings
from ..generators.edgegpu import edgegpu_settings
from ..generators.edgesbc import edgesbc_settings
from ..generators.edgetpu import edgetpu_settings
from ..generators.hybridbalanced import hybridbalanced_settings
from ..generators.hybridbalanced_jetson import hybridbalanced_jetson_settings
from ..utils import extract_model_type


def count_devices(nodes: List[Node]):
    """
    按设备类别统计生成结果。

    参数:
        nodes: Ether 或 Skippy 节点集合。 类型：List[Node]。

    返回:
        计算、查询或构造得到的结果。
    """
    counter = Counter()
    for node in nodes:
        node_type = extract_model_type(node.name)
        counter[node_type] += 1
    return counter


def counter_to_csv(counter: Counter) -> List[str]:
    """
    把 Counter 转换为 CSV 行结构。

    参数:
        counter: 统计计数器。 类型：Counter。

    返回:
        List[str]。
    """
    lines = ['device_type,percentage,count\n']
    n = sum(counter.values())
    for node_type, count in counter.items():
        lines.append(f'{node_type},{count / n},{count}\n')
    return lines


def format_device(device: str) -> str:
    """
    把 Device 格式化为可导出的字典。

    参数:
        device: 异构设备对象。 类型：str。

    返回:
        str。
    """
    if 'tx2' in device:
        return 'Nvidia TX2'
    if 'nx' in device:
        return 'Nvidia Xavier NX'
    if 'nano' in device:
        return 'Nvidia Nano'
    if 'gpu' in device:
        return 'XeonGpu'
    if 'cpu' in device:
        return 'XeonCpu'
    if 'nuc' in device:
        return 'Intel NUC'
    if 'rpi3' in device:
        return 'RPI 3'
    if 'rpi4' in device:
        return 'RPI 4'
    if 'rock' in device:
        return 'RockPi'
    if 'tpu' in device or 'coral' in device:
        return 'Coral DevBoard'


def convert_to_dict(counter: Counter) -> Dict:
    """
    把多组统计 Counter 合并为普通字典。

    参数:
        counter: 统计计数器。 类型：Counter。

    返回:
        Dict。
    """
    data = defaultdict(list)
    n = sum(counter.values())
    for node_type, count in counter.items():
        data['device_type'].append(node_type)
        data['count'].append(count)
        data['percentage'].append(count / n)

    return data


def main():
    """
    处理 main。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    configs = [
        (500, hybridbalanced_settings, 'hybrid_balanced'),
        (1000, hybridbalanced_jetson_settings, 'hybrid_balanced_jetson'),
        (2000, edgegpu_settings, 'edge_gpu'),
        (2500, edgesbc_settings, 'edge_sbc'),
        (1000, edgetpu_settings, 'edge_tpu'),
        (500, edgecloudlet_settings, 'edge_cloudlet'),
        (500, cloudgpu_settings, 'cloud_gpu'),
        (500, cloudcpu_settings, 'cloud_cpu')
    ]
    # 说明：分隔相关业务代码块。
    
    
    
    
    
    
    
    
    

    dfs = []
    for num, settings, name in configs:
        devices = generate_devices(num, settings)
        ether_nodes = convert_to_ether_nodes(devices)
        folder = './data/collections/collection_12_18_2020/devices/'
        score = calculate_heterogeneity(xeon_reqs(), calculate_requirements(convert_to_devices(ether_nodes)))
        file = os.path.join(folder, f'{name}_score_{round(score, 3)}.pkl')
        with open(file, 'wb') as fd:
            pickle.dump(devices, fd)
        device_statistic_file = os.path.join(folder, f'{name}_device_statistics.csv')
        c = count_devices(ether_nodes)
        count = counter_to_csv(c)
        count_dict = convert_to_dict(c)
        df = pd.DataFrame(data=count_dict)
        df = df.sort_values(by='device_type')
        df.index = df['device_type']
        df = df.drop('device_type', axis=1)
        df = df.drop('count', axis=1)
        df['scenario'] = f'{name} ({num} devices)'
        df['score'] = round(score, 3)
        df['percentage'] *= 100
        dfs.append(df)
        with open(device_statistic_file, 'w') as fd:
            fd.writelines(count)

    concat = pd.concat(dfs)
    devices = concat.index.unique()
    a = concat.set_index(['scenario', concat.index]).unstack()
    start = len(devices) + 1
    end = len(a.columns)
    drop_columns = [a.columns[i] for i in list(range(start, end))]
    a = a.drop(columns=drop_columns, axis=1)
    a.columns = [format_device(d) for d in devices.to_list()] + ['score']
    a.to_csv(os.path.join(folder, 'summary_devices.csv'))
    a.to_latex(os.path.join(folder, 'summary_devices.tex'))
    pass


if __name__ == '__main__':
    main()
