"""
文件作用：设备集合统计与异构度计算工具，用于衡量生成设备与需求向量之间的属性覆盖和差异。
主要函数：count_attribute、get_gpu_model_count、calculate_requirements、calculate_heterogeneity。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from collections import Counter
from enum import Enum
from typing import List, Callable

import numpy as np

from .device import GpuDevice, Device
from .model import Arch, Accelerator, Bins, Location, Connection, Disk, Requirements


def count_attribute(devices: List[Device], values: List, getter: Callable[[Device], Enum]):
    """
    函数作用：统计集合中指定属性或设备类型的数量。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：devices：设备对象列表，用于拓扑生成、异构度统计或节点转换。；values：候选属性值或统计值集合，用于概率抽样和异构度计算。；getter：属性读取函数，用于从设备对象中提取待统计字段。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    counter = {}
    if len(devices) == 0:
        return {}
    for attr in values:
        counter[attr] = 0
    for device in devices:
        counter[getter(device)] += 1
    percentage = {}
    n_devices = len(devices)
    for attr, count in counter.items():
        percentage[attr] = count / n_devices
    return percentage


def get_gpu_model_count(devices: List[Device]):
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：devices：设备对象列表，用于拓扑生成、异构度统计或节点转换。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    model_counts = Counter()
    gpu_mhz_counts = Counter()
    gpu_vram_counts = Counter()
    counter = 0
    for device in devices:
        if type(device) is GpuDevice:
            counter += 1
            gpu_device: GpuDevice
            gpu_device = device
            model_counts[gpu_device.gpu_model] += 1
            gpu_mhz_counts[gpu_device.gpu_mhz] += 1
            gpu_vram_counts[gpu_device.vram] += 1

    gpu_model_percentage = {}
    mhz_percentage = {}
    vram_percentage = {}
    for k, v in model_counts.items():
        gpu_model_percentage[k] = v / len(devices)

    for k, v in gpu_mhz_counts.items():
        mhz_percentage[k] = v / len(devices)

    for k, v in gpu_vram_counts.items():
        vram_percentage[k] = v / len(devices)

    return gpu_model_percentage, mhz_percentage, vram_percentage


def calculate_requirements(devices: List[Device]) -> Requirements:
    """
    函数作用：计算实验统计指标或异构性指标。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：devices：设备对象列表，用于拓扑生成、异构度统计或节点转换。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    arch = count_attribute(devices, list(Arch), lambda d: d.arch)
    accelerator = count_attribute(devices, list(Accelerator), lambda d: d.accelerator)
    cores = count_attribute(devices, list(Bins), lambda d: d.cores)
    location = count_attribute(devices, list(Location), lambda d: d.location)
    connection = count_attribute(devices, list(Connection), lambda d: d.connection)
    network = count_attribute(devices, list(Bins), lambda d: d.network)
    cpu_mhz = count_attribute(devices, list(Bins), lambda d: d.cpu_mhz)
    cpu = count_attribute(devices, list(set([x.cpu for x in devices])), lambda d: d.cpu)
    ram = count_attribute(devices, list(Bins), lambda d: d.ram)
    disk = count_attribute(devices, list(Disk), lambda d: d.disk)
    gpu_model_percentage, gpu_mhz_percentage, vram_percentage = get_gpu_model_count(devices)
    return Requirements(
        arch=arch,
        accelerator=accelerator,
        cores=cores,
        location=location,
        connection=connection,
        network=network,
        cpu_mhz=cpu_mhz,
        cpu=cpu,
        ram=ram,
        disk=disk,
        gpu_model=gpu_model_percentage,
        gpu_vram=gpu_mhz_percentage,
        gpu_mhz=vram_percentage
    )


def calculate_heterogeneity(p: Requirements, q: Requirements) -> float:
    """
    函数作用：计算实验统计指标或异构性指标。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：p：第一个概率分布或特征向量。；q：第二个概率分布或特征向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    entropy_p = 0
    entropy_q = 0
    for (p_enum, p_characteristic), (q_enum, q_characteristic) in zip(p.characteristics, q.characteristics):
        for value in list(p_enum):
            default_val = 0.0000000000000000000001
            p_char = p_characteristic.get(value, default_val)
            if p_char == 0:
                p_char = default_val
            entropy_p += p_char * np.log(p_char)
            q_char = q_characteristic.get(value, default_val)
            if q_char == 0:
                q_char = default_val
            entropy_q += q_char * np.log(q_char)

    return entropy_p - entropy_q
