"""
文件作用：异构设备生成器，按架构和属性概率生成设备集合，用于资源规划和大规模仿真实验。
主要类：GeneratorSettings。
主要函数：xeon_reqs、create_generator、create_t_setting、create_settings、create_and_save_settings、save_setting、choose_attribute_settings、process_arches、filter_invalid_settings、generate_settings、generate_probabilities、generate_arch_probs 等。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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
    类作用：异构设备生成配置，保存架构概率和架构内各属性概率分布。
    核心字段：arch：CPU 架构属性，例如 x86、arm32、aarch64。；properties：按架构组织的设备属性概率分布。。
    """
    # 字段说明：arch：CPU 架构属性，例如 x86、arm32、aarch64。
    arch: Dict[Arch, float]
    # 字段说明：properties：按架构组织的设备属性概率分布。
    properties: Dict[Arch, ArchProperties]


def xeon_reqs():
    """
    函数作用：处理 xeon、reqs 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：arches：CPU 架构候选集合，用于设备生成和场景配置。；t：目标异构度或临时数值参数，参与设备生成配置计算。；heterogeneity_score：目标异构度分数，用于控制生成设备集合的差异程度。；base_req：基础需求向量，用于推导设备生成配置。；folder：输入或输出目录。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：i：循环索引或配置编号。；t：目标异构度或临时数值参数，参与设备生成配置计算。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    setting = {}
    for k, prob in t[i]:
        setting[k] = prob
    return setting


def create_settings(arches, base_req, tuples, heterogeneity_score: Callable[[Requirements, Requirements], float]
                    , folder: str):
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    参数：arches：CPU 架构候选集合，用于设备生成和场景配置。；base_req：基础需求向量，用于推导设备生成配置。；tuples：属性概率元组集合，用于组合设备生成配置。；heterogeneity_score：目标异构度分数，用于控制生成设备集合的差异程度。；folder：输入或输出目录。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    product = itertools.product(*tuples)
    list((map(lambda t: create_generator(arches, t, heterogeneity_score, base_req, folder), product)))


def create_and_save_settings(arches, base_requirement, tuples, heterogeneity_score, folder):
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    参数：arches：CPU 架构候选集合，用于设备生成和场景配置。；base_requirement：基础需求向量，用于生成目标异构场景。；tuples：属性概率元组集合，用于组合设备生成配置。；heterogeneity_score：目标异构度分数，用于控制生成设备集合的差异程度。；folder：输入或输出目录。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    combs = list(tuples.values())
    create_settings(arches, base_requirement, combs, heterogeneity_score, folder)


def save_setting(folder, setting):
    """
    函数作用：处理 save、setting 相关业务逻辑。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    参数：folder：输入或输出目录。；setting：单个设备生成配置对象。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    now = datetime.datetime.now()
    now = now.strftime('%Y_%m_%d_%H_%M_%S_%f')
    file_name = f'{now}_{random.randint(1000, 10000)}.pickle'
    with open(f'{folder}/{file_name}', 'wb+') as fd:
        pickle.dump(setting, fd)


def choose_attribute_settings(values, percentage):
    """
    函数作用：处理 choose、attribute、settings 相关业务逻辑。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：values：候选属性值或统计值集合，用于概率抽样和异构度计算。；percentage：抽样比例或属性保留比例。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if type(values) is tuple:
        return np.array([values])
    n = len(values)
    take = max(1, int(n * percentage))
    choice = np.random.choice(n, size=take)
    return np.array(values)[choice, :]


def process_arches(arch_probs, probs_for_archs, base_req, heterogeneity_score, folder):
    """
    函数作用：处理 process、arches 相关业务逻辑。
    参数：arch_probs：表示 arch、probs，在当前业务流程中作为输入参数、状态字段或计算结果使用。；probs_for_archs：按架构组织的属性概率配置。；base_req：基础需求向量，用于推导设备生成配置。；heterogeneity_score：目标异构度分数，用于控制生成设备集合的差异程度。；folder：输入或输出目录。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
    函数作用：处理 filter、invalid、settings 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：old_probs_per_arch：过滤前的架构属性概率配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
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
    
    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
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
    函数作用：处理 generate、settings 相关业务逻辑。
    参数：base_requirement：基础需求向量，用于生成目标异构场景。；heterogeneity_score：目标异构度分数，用于控制生成设备集合的差异程度。；steps：概率离散化步数，用于生成候选概率组合。；arch_steps：架构概率离散化步数。；percentage：抽样比例或属性保留比例。；folder：输入或输出目录。；cores：CPU 核心数量等级或数值。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    """
    函数作用：处理 generate、probabilities 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：steps：概率离散化步数，用于生成候选概率组合。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：处理 generate、arch、probs 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：arch_steps：架构概率离散化步数。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：bin：资源等级桶，用于从低/中/高/很高等离散等级中抽样。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：bin：资源等级桶，用于从低/中/高/很高等离散等级中抽样。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：bin：资源等级桶，用于从低/中/高/很高等离散等级中抽样。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：probs：概率分布，用于随机选择属性值。；name：对象名称。；enum：枚举类型，用于把概率分布映射到具体属性取值。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    values = list(enum)
    return [tuple(values)] * len(probs[name][values[0]])


def random_arch():
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return random.choice(list(Arch))


def random_bin():
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return random.choice(list(Bins))


def random_connection():
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return random.choice(list(Connection))


def random_location():
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return random.choice(list(Location))


def random_cpu(arch: Arch) -> CpuModel:
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：arch：CPU 架构属性，例如 x86、arm32、aarch64。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if arch is Arch.AARCH64:
        return CpuModel.ARM
    elif arch is Arch.ARM32:
        return CpuModel.ARM
    else:
        return random.choice([CpuModel.I7, CpuModel.XEON])


def random_accelerator(arch: Arch) -> Accelerator:
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：arch：CPU 架构属性，例如 x86、arm32、aarch64。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if arch is Arch.AARCH64:
        return random.choice(list(Accelerator))
    elif arch is Arch.ARM32:
        return Accelerator.NONE
    else:
        return random.choice([Accelerator.GPU, Accelerator.NONE])


def random_gpu_model(arch: Arch) -> GpuModel:
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：arch：CPU 架构属性，例如 x86、arm32、aarch64。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if arch is Arch.X86:
        return GpuModel.TURING
    else:
        return random.choice([GpuModel.PASCAL, GpuModel.MAXWELL, GpuModel.VOLTA])


def random_disk() -> Disk:
    """
    函数作用：从预设分布中随机抽取一个设备或资源属性。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return random.choice(list(Disk))


def get_property_with_probs(probs: Dict[Enum, float]):
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：probs：概率分布，用于随机选择属性值。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    values = list(probs[1].keys())
    probs = list(probs[1].values())
    if len(values) == 0:
        return None
    index = np.random.choice(len(values), size=1, p=probs)[0]
    return values[index]


def generate_devices_with_settings(n: int, settings: GeneratorSettings) -> List[Device]:
    """
    函数作用：处理 generate、devices、with、settings 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：n：数量参数。；settings：实验或设备生成设置，保存场景参数和概率分布。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：处理 generate、devices 相关业务逻辑。
    关键流程：
    - 使用随机采样生成设备属性、请求间隔或性能取值。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：n：数量参数。；settings：实验或设备生成设置，保存场景参数和概率分布。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
    函数作用：处理 main 相关业务逻辑。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    generate_settings_main()


def generate_settings_main():
    
    """
    函数作用：处理 generate、settings、main 相关业务逻辑。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
