"""
Raith21 执行时间与资源画像 Oracle。

本模块把静态 FET 分布和资源画像表包装为 faas-sim 的 FetOracle/ResourceOracle 接口，统一处理节点名称与镜像查询。
"""

from typing import Tuple, Dict, Optional

from srds import ParameterizedDistribution as PDist, BoundRejectionSampler, BufferedSampler

from ext.raith21.utils import extract_model_type
from sim.oracle.oracle import FetOracle, ResourceOracle


class Raith21FetOracle(FetOracle):

    """
    Raith21 函数执行时间 Oracle。

    按设备类型和镜像查询执行时间分布，并通过采样器产生单次 FET。

    关键字段:
        execution_times: 节点类型与镜像到执行时间分布的映射。
        execution_time_samplers: 执行时间分布对应的缓存采样器。
    """
    def __init__(self, execution_times: Dict[Tuple[str, str], Tuple[float, float, PDist]]):
        """
        初始化 Raith21FetOracle。

        建立字段：execution_times、execution_time_samplers。

        参数:
            execution_times: 执行时间分布表。 类型：Dict[Tuple[str, str], Tuple[float, float, PDist]]。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        super().__init__()
        self.execution_times = execution_times
        self.execution_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            execution_times.items()
        }

    def sample(self, host: str, image: str) -> Optional[float]:
        """
        按节点和镜像采样一次函数执行时间。

        节点实例名会先归一化为设备类型，镜像 tag 也会被去掉，以匹配静态画像表的键。
        找不到节点/镜像组合时返回 None，调度谓词会据此过滤不可运行节点。

        参数:
            host: 设备类型或节点名称。 类型：str。
            image: 函数镜像名称。 类型：str。

        返回:
            Optional[float]。
        """
        host_type = extract_model_type(host) if '_' in host else host
        image_key = image.split(':')[0]  

        k = (host_type, image_key)
        if k not in self.execution_time_samplers:
            return None

        return self.execution_time_samplers[k].sample()


class Raith21ResourceOracle(ResourceOracle):

    """
    Raith21 函数资源画像 Oracle。

    按设备类型和镜像返回 CPU、内存、网络、块 I/O 和 GPU 等资源占用。

    关键字段:
        resources: 节点类型与镜像到资源画像的映射。
    """
    def __init__(self, resources: Dict[Tuple[str, str], 'FunctionResourceCharacterization']):
        """
        初始化 Raith21ResourceOracle。

        建立字段：resources。

        参数:
            resources: 函数资源画像表。 类型：Dict[Tuple[str, str], 'FunctionResourceCharacterization']。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        super().__init__()
        self.resources = resources

    def get_resources(self, host: str, image: str):
        """
        按节点和镜像返回函数资源画像。

        节点实例名会转换为设备类型；画像不存在时返回 None。

        参数:
            host: 设备类型或节点名称。 类型：str。
            image: 函数镜像名称。 类型：str。

        返回:
            FunctionResourceCharacterization，或在画像缺失时返回 None。
        """
        host = extract_model_type(host) if '_' in host else host
        return self.resources.get((host, image), None)
