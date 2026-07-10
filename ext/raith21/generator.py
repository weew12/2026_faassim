"""
异构设备概率生成器。

本模块根据 GeneratorSettings 中的属性概率生成 Device/GpuDevice 集合，并提供随机属性采样、约束过滤、配置保存和命令行入口。
"""

import datetime
import itertools
import multiprocessing
import pickle
import random
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from multiprocessing.context import Process
from pathlib import Path
from typing import List, Dict, Tuple, Callable

import numpy as np

from .calculations import calculate_heterogeneity
from .device import ArchProperties, GpuDevice, Device
from .model import Arch, Requirements, Accelerator, Bins, Disk, Location, Connection, CpuModel, GpuModel


@dataclass
class GeneratorSettings:
    """
    设备生成器配置。

    保存目标 Requirements、随机种子和设备数量，用于可复现地生成异构设备集合。

    关键字段:
        arch: CPU 架构及其概率分布。
        properties: 各 CPU 架构对应的 ArchProperties。
    """
    arch: Dict[Arch, float]
    properties: Dict[Arch, ArchProperties]


def xeon_reqs():
    """
    返回只生成单一 Xeon CPU 设备的基准 Requirements。

    返回:
        计算、查询或构造得到的结果。
    """
    xeon_single_device_req = Requirements(
        arch={
            Arch.X86: 1
        },
        accelerator={
            Accelerator.NONE: 1
        },
        cores={
            Bins.LOW: 1
        },
        disk={
            Disk.SSD: 1
        },
        location={
            Location.CLOUD: 1
        },
        connection={
            Connection.ETHERNET: 1
        },
        network={
            Bins.LOW: 1
        },
        cpu_mhz={
            Bins.LOW: 1
        },
        cpu={
            CpuModel.XEON: 1
        },
        ram={
            Bins.LOW: 1
        },
        gpu_model={},
        gpu_vram={},
        gpu_mhz={}
    )
    return xeon_single_device_req


def create_generator(arches, t, heterogeneity_score, base_req, folder):
    """
    把一组架构概率和属性概率组合装配为 GeneratorSettings，并保存到文件。

    参数:
        arches: CPU 架构及概率配置。
        t: 单个属性概率组合。
        heterogeneity_score: 比较目标分布与实际分布的函数。
        base_req: 基准 Requirements。
        folder: 模型或输出文件所在目录。

    返回:
        计算、查询或构造得到的结果。
    """
    gen_settings = {}
    arch_settings = {}
    for index, arch in enumerate(arches):
        arch_settings[arch[0]] = arch[1]
        settings = list(map(lambda i: create_t_setting(i, t[index]), range(len(t[index]))))
        settings = [arch] + settings
        gen_settings[arch[0]] = ArchProperties(*settings)
    setting = GeneratorSettings(arch_settings, gen_settings)
    save_setting(folder, setting)
    return setting


def create_t_setting(i, t):
    """
    把第 i 类属性的概率元组转换为枚举到概率的字典。

    参数:
        i: 用于控制当前生成、筛选或配置过程的参数。
        t: 单个属性概率组合。

    返回:
        计算、查询或构造得到的结果。
    """
    setting = {}
    for k, prob in t[i]:
        setting[k] = prob
    return setting


def create_settings(arches, base_req, tuples, heterogeneity_score: Callable[[Requirements, Requirements], float]
                    , folder: str):
    """
    遍历各属性概率组合的笛卡尔积，为每个组合创建生成器配置。

    参数:
        arches: CPU 架构及概率配置。
        base_req: 基准 Requirements。
        tuples: 各属性候选概率组合。
        heterogeneity_score: 比较目标分布与实际分布的函数。 类型：Callable[[Requirements, Requirements], float]。
        folder: 模型或输出文件所在目录。 类型：str。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    product = itertools.product(*tuples)
    list((map(lambda t: create_generator(arches, t, heterogeneity_score, base_req, folder), product)))


def create_and_save_settings(arches, base_requirement, tuples, heterogeneity_score, folder):
    """
    提取各架构的概率组合并批量生成、保存 GeneratorSettings。

    参数:
        arches: CPU 架构及概率配置。
        base_requirement: 基准 Requirements。
        tuples: 各属性候选概率组合。
        heterogeneity_score: 比较目标分布与实际分布的函数。
        folder: 模型或输出文件所在目录。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    combs = list(tuples.values())
    create_settings(arches, base_requirement, combs, heterogeneity_score, folder)


def save_setting(folder, setting):
    """
    用时间戳和随机后缀命名，将 GeneratorSettings 序列化为 pickle。

    参数:
        folder: 模型或输出文件所在目录。
        setting: 待保存的 GeneratorSettings。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    now = datetime.datetime.now()
    now = now.strftime('%Y_%m_%d_%H_%M_%S_%f')
    file_name = f'{now}_{random.randint(1000, 10000)}.pickle'
    with open(f'{folder}/{file_name}', 'wb+') as fd:
        pickle.dump(setting, fd)


def choose_attribute_settings(values, percentage):
    """
    从属性概率候选集中按比例抽样，至少保留一个候选。

    参数:
        values: 待统计或待采样的候选值集合。
        percentage: 候选值抽样比例。

    返回:
        计算、查询或构造得到的结果。
    """
    if type(values) is tuple:
        return np.array([values])
    n = len(values)
    take = max(1, int(n * percentage))
    choice = np.random.choice(n, size=take)
    return np.array(values)[choice, :]


def process_arches(arch_probs, probs_for_archs, base_req, heterogeneity_score, folder):
    """
    遍历架构概率候选，为每种架构组合生成属性配置文件。

    参数:
        arch_probs: 架构概率候选集合。
        probs_for_archs: 各架构的属性概率候选集合。
        base_req: 基准 Requirements。
        heterogeneity_score: 比较目标分布与实际分布的函数。
        folder: 模型或输出文件所在目录。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    for arches in arch_probs:
        tuples = {}
        for arch in list(Arch):
            arch_tuples = list(itertools.product(*probs_for_archs[arch]))
            tuples[arch] = arch_tuples
        create_and_save_settings(
            arches,
            base_req,
            tuples,
            heterogeneity_score,
            folder
        )


def filter_invalid_settings(old_probs_per_arch):
    
    """
    删除架构与硬件不兼容的属性组合，例如 ARM32 + x86 CPU 或无 GPU + GPU 属性。

    参数:
        old_probs_per_arch: 待过滤的不合法架构属性组合。

    返回:
        计算、查询或构造得到的结果。
    """
    old_probs_per_arch[Arch.ARM32]['accelerator'] = ((Accelerator.NONE, 1), (Accelerator.GPU, 0), (Accelerator.TPU, 0))
    del old_probs_per_arch[Arch.ARM32]['gpu_vram']
    del old_probs_per_arch[Arch.ARM32]['gpu_model']
    del old_probs_per_arch[Arch.ARM32]['gpu_mhz']
    old_probs_per_arch[Arch.ARM32]['cpu'] = ((CpuModel.I7, 0), (CpuModel.XEON, 0), (CpuModel.ARM, 1))
    old_probs_per_arch[Arch.AARCH64]['cpu'] = ((CpuModel.I7, 0), (CpuModel.XEON, 0), (CpuModel.ARM, 1))

    old_probs_per_arch[Arch.ARM32]['disk'] = (
        (Disk.SD, 1), (Disk.FLASH, 0), (Disk.HDD, 0), (Disk.SSD, 0), (Disk.NVME, 0))

    
    old_probs_per_arch[Arch.ARM32]['cores'] = list(
        filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.ARM32]['cores']))
    
    old_probs_per_arch[Arch.ARM32]['ram'] = list(filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.ARM32]['ram']))
    
    old_probs_per_arch[Arch.ARM32]['ram'] = list(filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.ARM32]['ram']))
    
    old_probs_per_arch[Arch.ARM32]['cores'] = list(
        filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.ARM32]['cores']))
    
    old_probs_per_arch[Arch.ARM32]['location'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.ARM32]['location']))
    
    old_probs_per_arch[Arch.ARM32]['location'] = list(
        filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.ARM32]['location']))
    
    old_probs_per_arch[Arch.X86]['accelerator'] = list(
        filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.X86]['accelerator']))
    
    old_probs_per_arch[Arch.X86]['connection'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.X86]['connection']))
    
    old_probs_per_arch[Arch.X86]['connection'] = list(
        filter(lambda f: f[1][1] == 0, old_probs_per_arch[Arch.X86]['connection']))
    old_probs_per_arch[Arch.X86]['cpu'] = list(filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.X86]['cpu']))
    
    old_probs_per_arch[Arch.X86]['gpu_model'] = list(
        filter(lambda f: f[1][1] == 0, old_probs_per_arch[Arch.X86]['gpu_model']))
    
    old_probs_per_arch[Arch.X86]['gpu_model'] = list(
        filter(lambda f: f[2][1] == 0, old_probs_per_arch[Arch.X86]['gpu_model']))
    
    old_probs_per_arch[Arch.X86]['gpu_model'] = list(
        filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.X86]['gpu_model']))
    
    old_probs_per_arch[Arch.X86]['network'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.X86]['network']))
    
    old_probs_per_arch[Arch.X86]['disk'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.X86]['disk']))
    
    old_probs_per_arch[Arch.X86]['disk'] = list(
        filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.X86]['disk']))
    
    old_probs_per_arch[Arch.X86]['disk'] = list(
        filter(lambda f: f[4][1] == 0, old_probs_per_arch[Arch.X86]['disk']))

    
    old_probs_per_arch[Arch.AARCH64]['cores'] = list(
        filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.AARCH64]['cores']))
    
    old_probs_per_arch[Arch.AARCH64]['disk'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.AARCH64]['disk']))
    
    old_probs_per_arch[Arch.AARCH64]['disk'] = list(
        filter(lambda f: f[1][1] == 0, old_probs_per_arch[Arch.AARCH64]['disk']))
    
    old_probs_per_arch[Arch.AARCH64]['disk'] = list(
        filter(lambda f: f[3][1] == 0, old_probs_per_arch[Arch.AARCH64]['disk']))
    
    old_probs_per_arch[Arch.AARCH64]['location'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.AARCH64]['location']))
    
    old_probs_per_arch[Arch.AARCH64]['gpu_model'] = list(
        filter(lambda f: f[0][1] == 0, old_probs_per_arch[Arch.AARCH64]['gpu_model']))
    return old_probs_per_arch


def generate_settings(base_requirement: Requirements,
                      heterogeneity_score: Callable[[Requirements, Requirements], float], steps: int = 5,
                      arch_steps: int = 5,
                      percentage: float = 1,
                      folder: str = './data', cores: int = None) -> None:
    """
    生成离散概率网格，并筛选出满足异构度范围的 GeneratorSettings。

    参数:
        base_requirement: 基准 Requirements。 类型：Requirements。
        heterogeneity_score: 比较目标分布与实际分布的函数。 类型：Callable[[Requirements, Requirements], float]。
        steps: 属性概率离散步数。 类型：int。
        arch_steps: 架构概率离散步数。 类型：int。
        percentage: 候选值抽样比例。 类型：float。
        folder: 模型或输出文件所在目录。 类型：str。
        cores: 用于控制当前生成、筛选或配置过程的参数。 类型：int。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    probs_for_archs = generate_arch_probs(arch_steps)
    old_probs_per_arch = generate_probabilities(steps)
    if cores is None:
        cores = multiprocessing.cpu_count()

    now = datetime.datetime.now()
    now = now.strftime('%Y_%m_%d_%H_%M_%S')
    folder = f'{folder}/{now}_archsteps-{arch_steps}_steps-{steps}_percentage-{percentage}'
    Path(folder).mkdir(parents=True, exist_ok=True)
    old_probs_per_arch = filter_invalid_settings(old_probs_per_arch)
    probs_per_arch = defaultdict(list)
    for arch, old_probs in old_probs_per_arch.items():
        for values in old_probs.values():
            probs_per_arch[arch].append(choose_attribute_settings(values, percentage))

    split = np.array_split(probs_for_archs, cores)
    ps = []
    for i in range(cores):
        if len(split[i]) > 0:
            
            p = Process(target=process_arches,
                        args=(split[i], probs_per_arch, base_requirement, heterogeneity_score, folder,))
            p.start()
            ps.append(p)

    for p in ps:
        p.join()


def generate_probabilities(steps: int):
    """
    生成枚举属性的离散概率分布候选。

    参数:
        steps: 属性概率离散步数。 类型：int。

    返回:
        计算、查询或构造得到的结果。
    """
    space = np.linspace(0, 1, num=steps)
    probs = defaultdict(lambda: defaultdict(list))
    for name, enum in Requirements.fields():
        if name == 'arch':
            continue
        values = list(enum)
        for t in itertools.product(space, repeat=len(values)):
            if np.sum(t) == 1:
                print(t)
                for index, prob in enumerate(t):
                    probs[name][values[index]].append(prob)
    tupled_probs = defaultdict(list)
    for key, value in probs.items():
        keys = list(value.keys())
        first_key = keys[0]
        for i in range(len(value[first_key])):
            l = []
            for k in keys:
                l.append((k, value[k][i]))
            tupled_probs[key].append(tuple(l))

    probs = {}
    for arch in list(Arch):
        probs[arch] = tupled_probs.copy()
    return probs


def generate_arch_probs(arch_steps: int):
    """
    生成 CPU 架构的离散概率分布候选。

    参数:
        arch_steps: 架构概率离散步数。 类型：int。

    返回:
        计算、查询或构造得到的结果。
    """
    space = np.linspace(0, 1, num=arch_steps)
    probs = defaultdict(lambda: defaultdict(list))

    values = list(Arch)
    for t in itertools.product(space, repeat=len(values)):
        if np.sum(t) == 1:
            print(t)
            has_one = False
            for val in t:
                if val == 1:
                    has_one = True
                    break
            if not has_one:
                for index, prob in enumerate(t):
                    probs['arch'][values[index]].append(prob)
    tupled_probs = defaultdict(list)
    for key, value in probs.items():
        keys = list(value.keys())
        first_key = keys[0]
        for i in range(len(value[first_key])):
            l = []
            for k in keys:
                l.append((k, value[k][i]))
            tupled_probs[key].append(tuple(l))

    return tupled_probs['arch']


def random_network_throughput(bin: Bins) -> Tuple[int, int]:
    """
    按网络能力等级采样具体吞吐率。

    参数:
        bin: 资源能力等级。 类型：Bins。

    返回:
        Tuple[int, int]。
    """
    if bin is Bins.LOW:
        return 125, 25
    if bin is Bins.MEDIUM:
        return 250, 50
    if bin is Bins.HIGH:
        return 500, 500
    if bin is Bins.VERY_HIGH:
        return 100, 100


def random_ram_size(bin: Bins) -> int:
    """
    按内存等级采样具体内存容量。

    参数:
        bin: 资源能力等级。 类型：Bins。

    返回:
        int。
    """
    if bin is Bins.LOW:
        return random.choice([1, 2, 4])
    if bin is Bins.MEDIUM:
        return random.choice([8, 16, 32])
    if bin is Bins.HIGH:
        return random.choice([64, 128])
    if bin is Bins.VERY_HIGH:
        return random.choice([256])


def random_cpu_cores(bin: Bins) -> int:
    """
    按核心数等级采样具体 CPU 核数。

    参数:
        bin: 资源能力等级。 类型：Bins。

    返回:
        int。
    """
    if bin is Bins.LOW:
        return random.randint(1, 2)
    elif bin is Bins.MEDIUM:
        return random.choice([4, 6, 8, 12])
    elif bin is Bins.HIGH:
        return random.choice([16, 32])
    elif bin is Bins.VERY_HIGH:
        return random.choice([64, 88, 128])


def create_tuples(probs, name, enum):
    """
    把枚举值与概率列表组合为可供笛卡尔积使用的候选元组。

    参数:
        probs: 枚举值到概率的映射。
        name: 对象、节点、bucket 或配置名称。
        enum: 属性枚举类型。

    返回:
        计算、查询或构造得到的结果。
    """
    values = list(enum)
    return [tuple(values)] * len(probs[name][values[0]])


def random_arch():
    """
    按架构概率采样 CPU 架构。

    返回:
        计算、查询或构造得到的结果。
    """
    return random.choice(list(Arch))


def random_bin():
    """
    按概率采样资源能力等级。

    返回:
        计算、查询或构造得到的结果。
    """
    return random.choice(list(Bins))


def random_connection():
    """
    按概率采样网络接入方式。

    返回:
        计算、查询或构造得到的结果。
    """
    return random.choice(list(Connection))


def random_location():
    """
    按概率采样设备位置。

    返回:
        计算、查询或构造得到的结果。
    """
    return random.choice(list(Location))


def random_cpu(arch: Arch) -> CpuModel:
    """
    在目标架构允许的 CPU 型号中按概率采样。

    参数:
        arch: 用于控制当前生成、筛选或配置过程的参数。 类型：Arch。

    返回:
        CpuModel。
    """
    if arch is Arch.AARCH64:
        return CpuModel.ARM
    elif arch is Arch.ARM32:
        return CpuModel.ARM
    else:
        return random.choice([CpuModel.I7, CpuModel.XEON])


def random_accelerator(arch: Arch) -> Accelerator:
    """
    在目标架构允许的加速器类型中按概率采样。

    参数:
        arch: 用于控制当前生成、筛选或配置过程的参数。 类型：Arch。

    返回:
        Accelerator。
    """
    if arch is Arch.AARCH64:
        return random.choice(list(Accelerator))
    elif arch is Arch.ARM32:
        return Accelerator.NONE
    else:
        return random.choice([Accelerator.GPU, Accelerator.NONE])


def random_gpu_model(arch: Arch) -> GpuModel:
    """
    在目标架构允许的 GPU 型号中按概率采样。

    参数:
        arch: 用于控制当前生成、筛选或配置过程的参数。 类型：Arch。

    返回:
        GpuModel。
    """
    if arch is Arch.X86:
        return GpuModel.TURING
    else:
        return random.choice([GpuModel.PASCAL, GpuModel.MAXWELL, GpuModel.VOLTA])


def random_disk() -> Disk:
    """
    按概率采样磁盘类型。

    返回:
        Disk。
    """
    return random.choice(list(Disk))


def get_property_with_probs(probs: Dict[Enum, float]):
    """
    使用随机数和累计概率选择一个枚举属性值。

    参数:
        probs: 枚举值到概率的映射。 类型：Dict[Enum, float]。

    返回:
        计算、查询或构造得到的结果。
    """
    values = list(probs[1].keys())
    probs = list(probs[1].values())
    if len(values) == 0:
        return None
    index = np.random.choice(len(values), size=1, p=probs)[0]
    return values[index]


def generate_devices_with_settings(n: int, settings: GeneratorSettings) -> List[Device]:
    """
    根据 GeneratorSettings 连续生成 n 个 Device/GpuDevice。

    参数:
        n: 需要生成、选择或统计的数量。 类型：int。
        settings: 设备生成或实验配置。 类型：GeneratorSettings。

    返回:
        List[Device]。
    """
    devices = []
    device_id = 0
    for arch, proportion in settings.arch.items():
        for i in range(int(n * proportion)):
            characteristics = list(map(lambda x: get_property_with_probs(x), settings.properties[arch].values))
            if characteristics[0] is Accelerator.GPU:
                device = GpuDevice(str(device_id), arch, *characteristics)
            else:
                
                device = Device(str(device_id), arch, *characteristics[:9])
            devices.append(device)
    return devices


def generate_devices(n: int, settings: GeneratorSettings = None) -> List[Device]:
    """
    读取生成器配置文件并生成指定数量的异构设备。

    参数:
        n: 需要生成、选择或统计的数量。 类型：int。
        settings: 设备生成或实验配置。 类型：GeneratorSettings。

    返回:
        List[Device]。
    """
    if settings is not None:
        return generate_devices_with_settings(n, settings)
    devices = []
    for i in range(n):
        device_id = str(i)
        arch = random_arch()
        cores = random_bin()
        location = random_location()
        connection = random_connection()
        network = random_bin()
        cpu_mhz = random_bin()
        cpu = random_cpu(arch)
        disk = random_disk()
        ram = random_bin()
        accelerator = random_accelerator(arch)
        if accelerator is Accelerator.GPU:
            vram = random_bin()
            gpu_mhz = random_bin()
            gpu_model = random_gpu_model(arch)
            devices.append(GpuDevice(
                id=device_id,
                arch=arch,
                accelerator=accelerator,
                cores=cores,
                location=location,
                connection=connection,
                network=network,
                cpu_mhz=cpu_mhz,
                cpu=cpu,
                ram=ram,
                vram=vram,
                gpu_mhz=gpu_mhz,
                gpu_model=gpu_model,
                disk=disk
            ))
        else:
            devices.append(Device(
                id=device_id,
                arch=arch,
                accelerator=accelerator,
                cores=cores,
                location=location,
                connection=connection,
                network=network,
                cpu_mhz=cpu_mhz,
                cpu=cpu,
                ram=ram,
                disk=disk
            ))

    return devices


def main():
    """
    运行默认设备生成任务并输出生成结果。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    generate_settings_main()


def generate_settings_main():
    
    """
    并行生成候选 GeneratorSettings 文件。

    返回:
        无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
    """
    steps = 4
    
    arch_steps = 6
    
    percentage = 0.1
    folder = '/mnt/ssd2data/Documents/hw_mapping_gen_settings'
    cores = 4
    base_req = xeon_reqs()
    score_f = calculate_heterogeneity
    generate_settings(
        base_requirement=base_req,
        heterogeneity_score=score_f,
        steps=steps,
        arch_steps=arch_steps,
        percentage=percentage,
        folder=folder,
        cores=cores
    )


if __name__ == '__main__':
    main()
