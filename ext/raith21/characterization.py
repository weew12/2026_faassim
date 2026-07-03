"""
文件作用：Raith21 函数画像装配入口，将执行时间 Oracle 和资源 Oracle 组合成 FunctionCharacterization。
主要函数：get_raith21_function_characterizations。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from typing import Dict

from ext.raith21 import images
from sim.faas import FunctionCharacterization
from sim.oracle.oracle import ResourceOracle, FetOracle


def get_raith21_function_characterizations(resource_oracle: ResourceOracle,
                                           fet_oracle: FetOracle) -> Dict[str, FunctionCharacterization]:
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。；fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。。
    返回：与该业务步骤对应的对象、指标或计算结果。
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
