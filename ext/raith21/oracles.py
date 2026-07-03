"""
文件作用：Raith21 专用 Oracle，读取论文实验中的函数执行时间和资源画像，在给定节点上采样执行时延与资源向量。
主要类：Raith21FetOracle、Raith21ResourceOracle。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from typing import Tuple, Dict, Optional

from srds import ParameterizedDistribution as PDist, BoundRejectionSampler, BufferedSampler

from ext.raith21.utils import extract_model_type
from sim.oracle.oracle import FetOracle, ResourceOracle


class Raith21FetOracle(FetOracle):

    """
    类作用：Raith21FetOracle 类，封装 raith21、fet、oracle 相关状态和业务操作。
    继承关系：FetOracle。
    核心方法：__init__、sample。
    """
    def __init__(self, execution_times: Dict[Tuple[str, str], Tuple[float, float, PDist]]):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：execution_time_samplers、execution_times。
        参数：execution_times：执行时间样本或统计表，用于性能估计。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.execution_times：执行时间样本或统计表，用于性能估计。
        self.execution_times = execution_times
        # 字段说明：self.execution_time_samplers：按节点或函数索引的执行时间采样器集合。
        self.execution_time_samplers = {
            k: BoundRejectionSampler(BufferedSampler(dist), xmin, xmax) for k, (xmin, xmax, dist) in
            execution_times.items()
        }

    def sample(self, host: str, image: str) -> Optional[float]:
        """
        函数作用：从经验分布或画像数据中采样一个函数执行时间。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host：执行函数的目标主机或节点。；image：容器镜像标识。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        host_type = extract_model_type(host) if '_' in host else host
        image_key = image.split(':')[0]  

        k = (host_type, image_key)
        if k not in self.execution_time_samplers:
            return None

        return self.execution_time_samplers[k].sample()


class Raith21ResourceOracle(ResourceOracle):

    """
    类作用：Raith21ResourceOracle 类，封装 raith21、resource、oracle 相关状态和业务操作。
    继承关系：ResourceOracle。
    核心方法：__init__、get_resources。
    """
    def __init__(self, resources: Dict[Tuple[str, str], 'FunctionResourceCharacterization']):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：resources。
        参数：resources：资源占用集合或资源向量。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        super().__init__()
        # 字段说明：self.resources：资源集合，表示 CPU、内存、网络、磁盘或 GPU 等占用。
        self.resources = resources

    def get_resources(self, host: str, image: str):
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：host：执行函数的目标主机或节点。；image：容器镜像标识。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        host = extract_model_type(host) if '_' in host else host
        return self.resources.get((host, image), None)
