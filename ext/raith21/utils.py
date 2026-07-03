"""
文件作用：Raith21 Benchmark 辅助函数，按实验 profile 快速创建 AI、混合、服务型函数部署集合。
主要函数：extract_model_type、create_ai_deployments、create_mixed_deployments、create_service_deployments、create_deployments_for_profile。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from typing import Dict

from ext.raith21 import images
from ext.raith21.deployments import create_all_deployments
from sim.faas import FunctionDeployment
from sim.oracle.oracle import FetOracle, ResourceOracle


def extract_model_type(device: str):
    """
    函数作用：处理 extract、model、type 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：device：单个设备对象，包含架构、资源、位置和连接方式等属性。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if not type(device) is str:
        return ''
    try:
        return device[:device.rindex('_')]
    except ValueError:
        return device


def create_ai_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    all_deployments = create_all_deployments(fet_oracle, resource_oracle)
    del all_deployments[images.tf_gpu_function]
    del all_deployments[images.pi_function]
    del all_deployments[images.fio_function]
    return all_deployments


def create_mixed_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return create_all_deployments(fet_oracle, resource_oracle)


def create_service_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    all_deployments = create_all_deployments(fet_oracle, resource_oracle)
    del all_deployments[images.speech_inference_function]
    del all_deployments[images.mobilenet_inference_function]
    del all_deployments[images.resnet50_inference_function]
    del all_deployments[images.resnet50_preprocessing_function]
    del all_deployments[images.resnet50_training_function]
    return all_deployments


def create_deployments_for_profile(profile: str, fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[
    str, FunctionDeployment]:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：profile：实验 profile 名称或配置，用于选择函数集合和负载类型。；fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if profile == 'ai':
        return create_ai_deployments(fet_oracle, resource_oracle)
    elif profile == 'mixed':
        return create_mixed_deployments(fet_oracle, resource_oracle)
    elif profile == 'service':
        return create_service_deployments(fet_oracle, resource_oracle)
    else:
        raise ValueError(f'unknown profile: {profile}')
