"""
Raith21 函数画像装配入口。

本模块把函数执行时间 Oracle 与资源 Oracle 绑定为 FunctionCharacterization，并按镜像名建立索引，供函数模拟器和调度优先级读取。
"""

from typing import Dict

from ext.raith21 import images
from sim.faas import FunctionCharacterization
from sim.oracle.oracle import ResourceOracle, FetOracle


def get_raith21_function_characterizations(resource_oracle: ResourceOracle,
                                           fet_oracle: FetOracle) -> Dict[str, FunctionCharacterization]:
    """
    为所有 Raith21 镜像创建函数执行时间与资源画像组合。

    参数:
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。

    返回:
        Dict[str, FunctionCharacterization]。
    """
    return {
        images.resnet50_inference_cpu_manifest: FunctionCharacterization(
            images.resnet50_inference_cpu_manifest, fet_oracle,
            resource_oracle),
        images.resnet50_inference_gpu_manifest: FunctionCharacterization(images.resnet50_inference_gpu_manifest,
                                                                         fet_oracle,
                                                                         resource_oracle),
        images.speech_inference_gpu_manifest: FunctionCharacterization(images.speech_inference_gpu_manifest, fet_oracle,
                                                                       resource_oracle),
        images.speech_inference_tflite_manifest: FunctionCharacterization(images.speech_inference_tflite_manifest,
                                                                          fet_oracle, resource_oracle),
        images.mobilenet_inference_tflite_manifest: FunctionCharacterization(
            images.mobilenet_inference_tflite_manifest,
            fet_oracle,
            resource_oracle),
        images.mobilenet_inference_tpu_manifest: FunctionCharacterization(images.mobilenet_inference_tpu_manifest,
                                                                          fet_oracle, resource_oracle),
        images.resnet50_training_gpu_manifest: FunctionCharacterization(images.resnet50_training_gpu_manifest,
                                                                        fet_oracle,
                                                                        resource_oracle),

        images.resnet50_training_cpu_manifest: FunctionCharacterization(images.resnet50_training_cpu_manifest,
                                                                        fet_oracle,
                                                                        resource_oracle),
        images.tf_gpu_manifest: FunctionCharacterization(images.tf_gpu_manifest,
                                                         fet_oracle,
                                                         resource_oracle),
        images.pi_manifest: FunctionCharacterization(images.pi_manifest,
                                                     fet_oracle,
                                                     resource_oracle),
        images.fio_manifest: FunctionCharacterization(images.fio_manifest,
                                                      fet_oracle,
                                                      resource_oracle),
        images.resnet50_preprocessing_manifest: FunctionCharacterization(images.resnet50_preprocessing_manifest,
                                                                         fet_oracle,
                                                                         resource_oracle)

    }
