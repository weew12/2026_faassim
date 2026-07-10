"""
Raith21 实验装配辅助函数。

本模块根据 profile 类型创建 AI、混合或服务型函数部署，并从模型名称提取 workload 类型。
"""

from typing import Dict

from ext.raith21 import images
from ext.raith21.deployments import create_all_deployments
from sim.faas import FunctionDeployment
from sim.oracle.oracle import FetOracle, ResourceOracle


def extract_model_type(device: str):
    """
    从模型或镜像名称中提取 workload 类型。

    参数:
        device: 异构设备对象。 类型：str。

    返回:
        模型名称中的 workload 类型；无法识别时返回 None。
    """
    if not type(device) is str:
        return ''
    try:
        return device[:device.rindex('_')]
    except ValueError:
        return device


def create_ai_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    创建 AI 类函数部署集合。

    参数:
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

    返回:
        Dict[str, FunctionDeployment]。
    """
    all_deployments = create_all_deployments(fet_oracle, resource_oracle)
    del all_deployments[images.tf_gpu_function]
    del all_deployments[images.pi_function]
    del all_deployments[images.fio_function]
    return all_deployments


def create_mixed_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    创建混合 AI/服务 workload 部署集合。

    参数:
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

    返回:
        Dict[str, FunctionDeployment]。
    """
    return create_all_deployments(fet_oracle, resource_oracle)


def create_service_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle) -> Dict[str, FunctionDeployment]:
    """
    创建非 AI 服务型函数部署集合。

    参数:
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

    返回:
        Dict[str, FunctionDeployment]。
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
    根据 profile 名称选择并创建对应部署集合。

    参数:
        profile: 工作负载类型，可选 service、ai 或 mixed。 类型：str。
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。

    返回:
        Dict[str, FunctionDeployment]。
    """
    if profile == 'ai':
        return create_ai_deployments(fet_oracle, resource_oracle)
    elif profile == 'mixed':
        return create_mixed_deployments(fet_oracle, resource_oracle)
    elif profile == 'service':
        return create_service_deployments(fet_oracle, resource_oracle)
    else:
        raise ValueError(f'unknown profile: {profile}')
