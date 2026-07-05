"""
文件作用：冷启动阶段耗时模型。

该文件提供一个确定性冷启动阶段模型，用于把函数副本从创建到可用的过程拆分为：
- deploy：镜像拉取或部署准备；
- startup：容器运行时启动；
- setup：函数业务初始化；
- first invoke：副本首次请求；
- warm invoke：后续热路径请求。
"""

from dataclasses import dataclass


@dataclass
class ColdStartPhaseConfig:
    """
    冷启动阶段配置。

    字段：
    - startup_duration：容器/运行时启动耗时；
    - setup_duration：函数业务初始化耗时；
    - first_invoke_duration：首次请求执行耗时；
    - warm_invoke_duration：热路径请求执行耗时；
    """

    startup_duration: float
    setup_duration: float
    first_invoke_duration: float
    warm_invoke_duration: float


class ColdStartModel:
    """
    确定性冷启动模型。

    当前样例使用固定阶段耗时，便于观察冷启动路径拆分结果。
    后续可以替换为 trace-driven、节点类型感知或镜像大小感知模型。
    """

    def __init__(self):
        """
        初始化模型。
        """
        self.default_config = ColdStartPhaseConfig(
            startup_duration=0.75,
            setup_duration=0.55,
            first_invoke_duration=0.30,
            warm_invoke_duration=0.08,
        )

    def get_config(self, function_name: str) -> ColdStartPhaseConfig:
        """
        返回指定函数的冷启动阶段配置。

        当前样例只使用一个函数，因此直接返回默认配置。
        """
        return self.default_config
