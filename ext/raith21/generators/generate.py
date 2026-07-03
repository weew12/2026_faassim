"""
文件作用：Raith21 设备生成配置文件，定义 generate 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。
主要函数：count_devices、counter_to_csv、format_device、convert_to_dict、main。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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
    函数作用：统计集合中指定属性或设备类型的数量。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：nodes：候选节点集合或拓扑节点列表，供调度、拓扑生成和统计过程使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    counter = Counter()
    for node in nodes:
        node_type = extract_model_type(node.name)
        counter[node_type] += 1
    return counter


def counter_to_csv(counter: Counter) -> List[str]:
    """
    函数作用：处理 counter、to、csv 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：counter：计数器对象，用于统计设备、属性或请求数量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    lines = ['device_type,percentage,count\n']
    n = sum(counter.values())
    for node_type, count in counter.items():
        lines.append(f'{node_type},{count / n},{count}\n')
    return lines


def format_device(device: str) -> str:
    """
    函数作用：处理 format、device 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：device：单个设备对象，包含架构、资源、位置和连接方式等属性。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：在不同对象模型之间转换数据表示。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：counter：计数器对象，用于统计设备、属性或请求数量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：处理 main 相关业务逻辑。
    关键流程：
    - 整理为表格数据，服务于后续实验分析。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
    
    
    
    
    
    
    
    
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
    

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
