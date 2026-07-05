"""
文件作用：函数元信息表。

该文件定义每类函数的冷启动代价、热路径耗时和缓存资源占用。
这些信息是缓存策略计算收益与代价的基础。
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class FunctionSpec:
    """
    函数规格。

    字段：
    - function_name：函数名称；
    - cold_start_duration：冷启动额外耗时；
    - warm_duration：热路径执行耗时；
    - memory_units：缓存该函数实例占用的抽象资源单位；
    - description：函数说明。
    """

    function_name: str
    cold_start_duration: float
    warm_duration: float
    memory_units: int
    description: str


def default_function_catalog() -> Dict[str, FunctionSpec]:
    """
    返回默认函数规格表。

    memory_units 使用抽象容量单位，而不是具体 MiB。
    这样可以让样例重点放在缓存策略机制上。
    """
    specs = [
        FunctionSpec(
            function_name="img-resize",
            cold_start_duration=0.80,
            warm_duration=0.08,
            memory_units=1,
            description="轻量图像缩放函数，调用频繁，资源占用较小。",
        ),
        FunctionSpec(
            function_name="json-parse",
            cold_start_duration=0.35,
            warm_duration=0.04,
            memory_units=1,
            description="轻量 JSON 解析函数，冷启动代价较低。",
        ),
        FunctionSpec(
            function_name="fft",
            cold_start_duration=1.40,
            warm_duration=0.18,
            memory_units=2,
            description="中等资源占用的频域计算函数，冷启动代价较高。",
        ),
        FunctionSpec(
            function_name="video-transcode",
            cold_start_duration=2.20,
            warm_duration=0.45,
            memory_units=3,
            description="重型视频转码函数，资源占用较大，冷启动代价高。",
        ),
        FunctionSpec(
            function_name="ml-infer",
            cold_start_duration=1.90,
            warm_duration=0.30,
            memory_units=2,
            description="机器学习推理函数，冷启动代价较高。",
        ),
    ]

    return {item.function_name: item for item in specs}
