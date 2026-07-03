"""Skippy 调度工具函数。

本文件提供调度器多个模块都会复用的基础工具：

1. 镜像名规范化：将未带 tag 的镜像补齐为 ``:latest``，与 Kubernetes/CRI 的镜像本地性
   判断方式保持一致；
2. 容量字符串解析：把 ``103M``、``512Mi`` 这类实验标签中的容量值转换为字节数；
3. 简单计时器和递增计数器：用于调试或生成序号。
"""

import re
import time

# 默认镜像标签。镜像名没有显式 tag 时，调度器按 latest 处理。
default_image_tag: str = "latest"


def normalize_image_name(image_name: str):
    """    将容器镜像名规范化为带 tag 的形式。

    业务作用：
    Skippy 使用镜像名作为 ``images_on_nodes`` 的键。如果同一个镜像有时写成 ``foo``，
    有时写成 ``foo:latest``，会导致镜像本地性判断错误。因此调度前统一补齐默认 tag。

    参数：
    - ``image_name``：原始容器镜像名。

    返回：
    - 带有 tag 的规范化镜像名。
    """
    # 只有当最后一个冒号出现在最后一个斜杠之前时，才说明镜像名没有 tag。
    if image_name.rfind(":") <= image_name.rfind("/"):
        image_name = image_name + ":" + default_image_tag
    return image_name


# 十进制和二进制容量单位到字节的换算表。
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

# 匹配 “整数 + 可选单位” 的容量字符串，例如 10M、512Mi、1000。
__size_pattern = re.compile(r"([0-9]+)([a-zA-Z]*)")


def parse_size_string(size_string: str) -> int:
    """    将容量字符串转换为字节数。

    业务作用：
    faas-sim 的函数标签中会使用 ``data.skippy.io/receives-from-storage=103M`` 这类
    字符串描述数据输入/输出大小。调度器和 Oracle 需要将其转换为字节数后才能估算
    带宽占用和传输时间。

    参数：
    - ``size_string``：容量字符串，例如 ``103M``、``512Mi`` 或 ``4096``。

    返回：
    - 对应的字节数。
    """
    m = __size_pattern.match(size_string)
    if not m:
        raise ValueError('invalid size string: %s' % size_string)

    if len(m.groups()) > 1:
        number = m.group(1)
        unit = m.group(2)
        return int(number) * __size_conversions.get(unit, 1)
    else:
        return int(m.group(1))


class Timer:
    """简单墙上时钟计时器，用于调试代码片段耗时。"""

    def __init__(self) -> None:
        """初始化计时器，尚未开始计时。"""
        super().__init__()
        # 最近一次 start 的时间戳；-1 表示尚未开始。
        self.then = -1

    def start(self):
        """记录当前时间并返回自身，便于链式调用。"""
        self.then = time.time()
        return self

    def ms(self):
        """返回从 ``start`` 到当前时刻经过的毫秒数。"""
        return (time.time() - self.then) * 1000


def counter(start: int = 1):
    """    生成从 ``start`` 开始的无限递增整数序列。

    业务作用：
    可用于给仿真对象、Pod 或临时事件生成稳定递增编号。
    """
    n = start
    while True:
        yield n
        n += 1
