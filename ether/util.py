"""Ether 通用工具文件，负责 Kubernetes/Docker 常见容量字符串与字节数之间的转换。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【工具层】—— 与核心仿真引擎解耦的辅助功能。

提供的工具:
    - parse_size_string: 解析 K8s/Docker 容量字符串 (1G, 512Mi, 999036Ki) → 字节数
    - to_size_string:    字节数 → 可读容量字符串 (反向)

设计哲学:
    1. 对接 Kubernetes / Docker 资源格式 (K=10^3 vs Ki=2^10)
    2. 正则 [0-9]+[a-zA-Z]* 简单解析,不引入额外依赖
    3. blocks/nodes.py 的 mem='1G' 依赖此模块解析

对 CSAC 论文的接口:
    - 节点内存建模直接用 K8s 风格字符串 (mem='1Gi')
    - 实验配置贴近真实 K8s 资源定义
================================================================================
"""

import re

# 容量单位到字节倍数的换算表。
__size_conversions = {
    'K': 10 ** 3,
    'M': 10 ** 6,
    'G': 10 ** 9,
    'T': 10 ** 12,
    'P': 10 ** 15,
    'E': 10 ** 18,
    'Ki': 2 ** 10,
    'Mi': 2 ** 20,
    'Gi': 2 ** 30,
    'Ti': 2 ** 40,
    'Pi': 2 ** 50,
    'Ei': 2 ** 60
}

# 容量字符串解析正则，用于拆分数字和单位。
__size_pattern = re.compile(r"([0-9]+)([a-zA-Z]*)")


def parse_size_string(size_string: str) -> int:
    """
    把 1G、512Mi、999036Ki 等容量字符串解析为字节数。

    返回：解析后的字节数。
    """
    m = __size_pattern.match(size_string)
    if len(m.groups()) > 1:
        number = m.group(1)
        unit = m.group(2)
        return int(number) * __size_conversions.get(unit, 1)
    else:
        return int(m.group(1))


def to_size_string(num_bytes, unit='M', precision=1) -> str:
    """
    把字节数格式化为指定单位的容量字符串。

    参数：
    - num_bytes：字节数输入，用于格式化为人类可读容量字符串。
    - unit：目标容量单位，例如 M、G、Mi、Gi。
    - precision：格式化容量字符串时保留的小数位数。

    返回：带单位的容量字符串。

    """
    factor = __size_conversions[unit]
    value = num_bytes / factor

    fmt = f'%0.{precision}f{unit}'

    return fmt % value
