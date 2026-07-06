"""Ether 预置节点构造文件，封装 VM、服务器、Raspberry Pi、Intel NUC、Jetson、Coral、RockPi 等典型云边设备的资源容量和标签。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【预置层】—— 11 种典型云边设备的工厂函数。

按设备类型分:
    云端:
      - create_vm_node:    4 核 / 8GB    / x86    / type=vm
      - create_server_node: 88 核 / 188GB / x86    / type=server
    边缘 SBC (单板机):
      - create_rpi3_node:  4 核 / 1GB    / arm32  / model=rpi3b+
      - create_rpi4_node:  4 核 / 1GB    / arm32v7/ model=rpi4
      - create_rockpi:     6 核 / 4GB    / aarch64/ model=rockpi4
      - create_nuc_node:   4 核 / 16GB   / x86    / model=nuci5
    边缘 AI:
      - create_coral:      4 核 / 1GB    / aarch64/ capabilities/tpu=edgetpu
      - create_tx2_node:   4 核 / 8GB    / aarch64/ capabilities/cuda=10, gpu=pascal
      - create_nano:       4 核 / 4GB    / aarch64/ capabilities/cuda=10, gpu=maxwell
      - create_nx:         6 核 / 8GB    / aarch64/ capabilities/cuda=10, gpu=volta

设计哲学:
    1. 工厂模式: 每个 create_xxx_node() 返回一个 Node 实例
    2. K8s 风格 labels: 用 'ether.edgerun.io/<key>' 命名空间
       → 调度器可直接按 label 匹配 (nodeSelector / affinity)
    3. arch 字段独立: 镜像架构约束 (arm/x86) 用 arch 单独判断
    4. 异构性: 核数 4-88, 内存 1GB-188GB, 反映真实边缘设备的巨大差异

对 CSAC 论文的接口:
    - 节点异构性实验: 混用 rpi3 / tx2 / nx / server
    - 镜像架构约束: if image.arch != node.arch: skip
    - GPU/TPU 调度: if 'cuda' in node.labels: 选 GPU 节点
    - 设备能力过滤: node.labels['ether.edgerun.io/type']
================================================================================
"""

import itertools
from collections import defaultdict
from typing import Dict

from ether.core import Node, Capacity
from ether.util import parse_size_string

# 按设备或网络单元类型维护的递增计数器，用于生成稳定唯一名称。
counters = defaultdict(lambda: itertools.count(0, 1))


def create_vm_node(name=None) -> Node:
    """
    创建云虚拟机节点，带有 x86 架构、默认 CPU/内存和云 VM 标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'cloudvm_%d' % next(counters['cloudvm'])

    return create_node(name=name,
                       cpus=4, arch='x86', mem='8167784Ki',
                       labels={
                           'ether.edgerun.io/type': 'vm',
                           'ether.edgerun.io/model': 'vm'
                       })


def create_server_node(name=None) -> Node:
    """
    创建云/边缘服务器节点，带有较高 CPU/内存容量和服务器标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'server_%d' % next(counters['server'])

    return create_node(name=name,
                       cpus=88, arch='x86', mem='188G',
                       labels={
                           'ether.edgerun.io/type': 'server',
                           'ether.edgerun.io/model': 'server'
                       })


def create_rpi3_node(name=None) -> Node:
    """
    创建 Raspberry Pi 3 节点，用于模拟资源受限 ARM 边缘设备。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'rpi3_%d' % next(counters['rpi3'])

    return create_node(name=name,
                       cpus=4, arch='arm32', mem='999036Ki',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'rpi3b+'
                       })


def create_nuc_node(name=None) -> Node:
    """
    创建 Intel NUC 节点，用于模拟小型 x86 边缘节点。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'nuc_%d' % next(counters['nuc'])

    return create_node(name=name,
                       cpus=4, arch='x86', mem='16Gi',
                       labels={
                           'ether.edgerun.io/type': 'sffc',
                           'ether.edgerun.io/model': 'nuci5'
                       })


def create_tx2_node(name=None) -> Node:
    """
    创建 Nvidia Jetson TX2 节点，并带有 CUDA/GPU 能力标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'tx2_%d' % next(counters['tx2'])

    return create_node(name=name,
                       cpus=4, arch='aarch64', mem='8047252Ki',
                       labels={
                           'ether.edgerun.io/type': 'embai',
                           'ether.edgerun.io/model': 'nvidia_jetson_tx2',
                           'ether.edgerun.io/capabilities/cuda': '10',
                           'ether.edgerun.io/capabilities/gpu': 'pascal',
                       })


def create_rockpi(name=None) -> Node:
    """
    创建 RockPi 节点，用于模拟 aarch64 单板机设备。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'rockpi_%d' % next(counters['rockpi'])

    return create_node(name=name,
                       cpus=6, arch='aarch64', mem='4G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'rockpi4'
                       })


def create_rpi4_node(name=None) -> Node:
    """
    创建 Raspberry Pi 4 节点，用于模拟 ARM 边缘设备。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'rpi4_%d' % next(counters['rpi4'])

    return create_node(name=name,
                       arch='arm32v7',
                       cpus=4,
                       mem='1G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'rpi4',
                       })


def create_coral(name=None) -> Node:
    """
    创建 Coral DevBoard 节点，并带有 Edge TPU 能力标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'coral_%d' % next(counters['coral'])

    return create_node(name=name,
                       cpus=4, arch='aarch64', mem='1G',
                       labels={
                           'ether.edgerun.io/type': 'sbc',
                           'ether.edgerun.io/model': 'coral',
                           'ether.edgerun.io/capabilities/tpu': 'edgetpu',
    })


def create_nano(name=None) -> Node:
    """
    创建 Nvidia Jetson Nano 节点，并带有 CUDA/GPU 能力标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'nano_%d' % next(counters['nano'])

    return create_node(name=name,
                       cpus=4, arch='aarch64', mem='4G',
                       labels={
                           'ether.edgerun.io/type': 'embai',
                           'ether.edgerun.io/model': 'nvidia_jetson_nano',
                           'ether.edgerun.io/capabilities/cuda': '10',
                           'ether.edgerun.io/capabilities/gpu': 'maxwell',
                       })


def create_nx(name=None) -> Node:
    """
    创建 Nvidia Jetson Xavier NX 节点，并带有 Volta GPU 能力标签。

    参数：
    - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。

    """
    name = name if name is not None else 'nx_%d' % next(counters['nx'])

    return create_node(name=name,
                       cpus=6, arch='aarch64', mem='8G',
                       labels={
                           'ether.edgerun.io/type': 'embai',
                           'ether.edgerun.io/model': 'nvidia_jetson_nx',
                           'ether.edgerun.io/capabilities/cuda': '10',
                           'ether.edgerun.io/capabilities/gpu': 'volta',
                       })


def create_node(name: str, cpus: int, mem: str, arch: str, labels: Dict[str, str]) -> Node:
    """
        根据 CPU 核数、内存字符串、架构和标签构造 Ether Node。

        参数：
        - name：节点、网络单元或数据源名称，用于生成拓扑顶点和日志标识。
        - cpus：CPU 核数，函数内部会转换为 millicores。
        - mem：内存容量字符串，例如 1G、16Gi 或 999036Ki。
        - arch：CPU 架构标签，用于函数镜像或设备能力匹配。
        - labels：节点标签集合，描述设备类型、型号和加速器能力。

        返回：构造好的 Ether Node。

        ─────────────────────────────────────────────────────────────
        【设计意图】为什么 cpus 要 × 1000?
        ─────────────────────────────────────────────────────────────
        11 个工厂都用 cpus × 1000 转成 millicores:
          - 4 核 → 4000 millicores
          - 88 核 → 88000 millicores
        不用核数而用毫核, 精度更高 (可表示 0.5 核、0.25 核等),
        符合 Kubernetes 资源模型, 调度器能精细分配。

        mem 用 util.parse_size_string 解析:
          - "1G" → 10^9 字节 (SI 十进制)
          - "16Gi" → 2^30 字节 (二进制,K8s 默认)
        直接对接 K8s/Docker 资源定义。
        ─────────────────────────────────────────────────────────────
        """
    # 把 CPU 核数转换为 millicores，并把内存字符串转换为字节容量。
    capacity = Capacity(cpu_millis=cpus * 1000, memory=parse_size_string(mem))
    return Node(name, capacity=capacity, arch=arch, labels=labels)


rpi3 = create_rpi3_node
nuc = create_nuc_node
tx2 = create_tx2_node
server = create_server_node
nx = create_nx
nano = create_nano
coral = create_coral
rpi4 = create_rpi4_node
rockpi = create_rockpi

