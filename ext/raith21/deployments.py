"""
文件作用：Raith21 函数部署定义文件，创建 ResNet、MobileNet、Speech、TensorFlow、Pi、Fio 等函数部署和镜像排序。
主要类：DeploymentSettings。
主要函数：get_resnet50_inference_deployment、get_speech_inference_deployment、get_mobilenet_inference_deployment、get_resnet_training_deployment、get_tf_gpu_deployment、get_pi_deployment、get_fio_deployment、get_resnet_preprocessing_deployment、create_all_deployments。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from dataclasses import dataclass
from typing import Dict

from ext.raith21 import images, storage
from sim.faas import DeploymentRanking, FunctionDeployment, FunctionImage, \
    FunctionContainer, KubernetesResourceConfiguration, Function, ScalingConfiguration
from sim.oracle.oracle import ResourceOracle, FetOracle

# 字段说明：default_resnet_inference_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_resnet_inference_ranking = DeploymentRanking(
    [images.resnet50_inference_gpu_manifest, images.resnet50_inference_cpu_manifest])
# 字段说明：default_speech_inference_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_speech_inference_ranking = DeploymentRanking(
    [images.speech_inference_tflite_manifest, images.speech_inference_gpu_manifest])
# 字段说明：default_mobilenet_inference_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_mobilenet_inference_ranking = DeploymentRanking(
    [images.mobilenet_inference_tpu_manifest, images.mobilenet_inference_tflite_manifest])
# 字段说明：default_resnet_training_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_resnet_training_ranking = DeploymentRanking(
    [images.resnet50_training_gpu_manifest, images.resnet50_training_cpu_manifest])
# 字段说明：default_pi_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_pi_ranking = DeploymentRanking([images.pi_manifest])
# 字段说明：default_fio_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_fio_ranking = DeploymentRanking([images.fio_manifest])
# 字段说明：default_tf_gpu_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_tf_gpu_ranking = DeploymentRanking([images.tf_gpu_manifest])
# 字段说明：default_resnet_preprocessing_ranking：函数镜像部署优先级，决定多镜像场景下优先选择哪个容器规格。
default_resnet_preprocessing_ranking = DeploymentRanking([images.resnet50_preprocessing_manifest])


@dataclass
class DeploymentSettings:
    """
    类作用：Raith21 实验的部署排序配置，保存不同函数在不同镜像上的优先级。
    核心字段：resnet_inference_ranking：ResNet 推理函数的镜像部署优先级。；resnet_preprocessing_ranking：ResNet 预处理函数的镜像部署优先级。；speech_inference_ranking：语音识别推理函数的镜像部署优先级。；mobilenet_inference_ranking：MobileNet 推理函数的镜像部署优先级。；resnet_training_ranking：ResNet 训练函数的镜像部署优先级。；tf_gpu_ranking：TensorFlow GPU 函数的镜像部署优先级。；pi_ranking：Python Pi 计算函数的镜像部署优先级。；fio_ranking：Fio I/O 函数的镜像部署优先级。。
    """
    # 字段说明：resnet_inference_ranking：ResNet 推理函数的镜像部署优先级。
    resnet_inference_ranking: DeploymentRanking = default_resnet_inference_ranking
    # 字段说明：resnet_preprocessing_ranking：ResNet 预处理函数的镜像部署优先级。
    resnet_preprocessing_ranking: DeploymentRanking = default_resnet_preprocessing_ranking
    # 字段说明：speech_inference_ranking：语音识别推理函数的镜像部署优先级。
    speech_inference_ranking: DeploymentRanking = default_speech_inference_ranking
    # 字段说明：mobilenet_inference_ranking：MobileNet 推理函数的镜像部署优先级。
    mobilenet_inference_ranking: DeploymentRanking = default_mobilenet_inference_ranking
    # 字段说明：resnet_training_ranking：ResNet 训练函数的镜像部署优先级。
    resnet_training_ranking: DeploymentRanking = default_resnet_training_ranking
    # 字段说明：tf_gpu_ranking：TensorFlow GPU 函数的镜像部署优先级。
    tf_gpu_ranking: DeploymentRanking = default_tf_gpu_ranking
    # 字段说明：pi_ranking：Python Pi 计算函数的镜像部署优先级。
    pi_ranking: DeploymentRanking = default_pi_ranking
    # 字段说明：fio_ranking：Fio I/O 函数的镜像部署优先级。
    fio_ranking: DeploymentRanking = default_fio_ranking


def get_resnet50_inference_deployment(ranking: DeploymentRanking,
                                      scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    resnet50_cpu_function_image = FunctionImage(image=images.resnet50_inference_cpu_manifest)
    resnet50_gpu_function_image = FunctionImage(image=images.resnet50_inference_gpu_manifest)

    resnet50_function = Function(images.resnet50_inference_function,
                                 fn_images=[resnet50_gpu_function_image, resnet50_cpu_function_image])

    
    model = storage.resnet_model_bucket_item.name
    data_storage = {
        'data.skippy.io/receives-from-storage': '103M',
        'data.skippy.io/receives-from-storage/path': f'{storage.resnet_model_bucket}/{model}',
    }

    resnet50_cpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="150Mi")
    resnet50_cpu_function = FunctionContainer(
        resnet50_cpu_function_image,
        resource_config=resnet50_cpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '4a'})

    resnet50_gpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="400Mi")
    resnet50_gpu_function = FunctionContainer(
        resnet50_gpu_function_image,
        resource_config=resnet50_gpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'device.edgerun.io/accelerator': 'GPU',
                'device.edgerun.io/vram': '1500',
                'cluster': '4b'})

    resnet50_gpu_function.labels.update(data_storage)
    resnet50_cpu_function.labels.update(data_storage)

    deployment = FunctionDeployment(
        resnet50_function,
        [resnet50_gpu_function, resnet50_cpu_function],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_speech_inference_deployment(ranking: DeploymentRanking,
                                    scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    speech_gpu_function_image = FunctionImage(image=images.speech_inference_gpu_manifest)
    speech_tflite_function_image = FunctionImage(image=images.speech_inference_tflite_manifest)
    speech_function = Function(images.speech_inference_function,
                               fn_images=[speech_gpu_function_image, speech_tflite_function_image])

    
    tflite = storage.speech_model_tflite_bucket_item
    data_storage_tflite = {
        'data.skippy.io/receives-from-storage': '48M',
        'data.skippy.io/receives-from-storage/path': f'{storage.speech_bucket}/{tflite.name}',
    }
    gpu = storage.speech_model_gpu_bucket_item
    data_storage_gpu = {
        
        
        'data.skippy.io/receives-from-storage': '188M',
        'data.skippy.io/receives-from-storage/path': f'{storage.speech_bucket}/{gpu.name}',

    }

    speech_gpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="300Mi")
    speech_gpu_function = FunctionContainer(
        speech_gpu_function_image,
        resource_config=speech_gpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '0', 'device.edgerun.io/accelerator': 'GPU',
                'device.edgerun.io/vram': '1500', })
    speech_gpu_function.labels.update(data_storage_gpu)

    speech_tflite_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="100Mi")
    speech_tflite_function = FunctionContainer(
        speech_tflite_function_image,
        resource_config=speech_tflite_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1'})
    speech_tflite_function.labels.update(data_storage_tflite)

    deployment = FunctionDeployment(
        speech_function,
        [speech_gpu_function, speech_tflite_function],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_mobilenet_inference_deployment(ranking: DeploymentRanking,
                                       scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    mobilenet_tpu_function_image = FunctionImage(image=images.mobilenet_inference_tpu_manifest)

    mobilenet_tflite_function_image = FunctionImage(image=images.mobilenet_inference_tflite_manifest)

    mobilenet_function = Function(images.mobilenet_inference_function,
                                  fn_images=[mobilenet_tpu_function_image, mobilenet_tflite_function_image])

    
    tflite = storage.mobilenet_model_tflite_bucket_item.name
    data_storage_tflite_labels = {
        'data.skippy.io/receives-from-storage': '4M',
        'data.skippy.io/receives-from-storage/path': f'{storage.mobilenet_bucket}/{tflite}',
    }

    tpu = storage.mobilenet_model_tpu_bucket_item.name
    data_storage_tpu_labels = {
        'data.skippy.io/receives-from-storage': '4M',
        'data.skippy.io/receives-from-storage/path': f'{storage.mobilenet_bucket}/{tpu}',
    }

    mobilenet_tpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="100Mi")
    mobilenet_tpu_function = FunctionContainer(
        mobilenet_tpu_function_image,
        resource_config=mobilenet_tpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1b', 'device.edgerun.io/accelerator': 'TPU'}
    )

    mobilenet_tflite_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="100Mi")
    mobilenet_tflite_function = FunctionContainer(
        mobilenet_tflite_function_image,
        resource_config=mobilenet_tflite_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1a'})

    mobilenet_tpu_function.labels.update(data_storage_tpu_labels)
    mobilenet_tflite_function.labels.update(data_storage_tflite_labels)

    deployment = FunctionDeployment(
        mobilenet_function,
        [mobilenet_tpu_function, mobilenet_tflite_function],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    deployment.function_factor = {
        images.mobilenet_inference_tpu_manifest: 1,
        images.mobilenet_inference_tflite_manifest: 1
    }

    return deployment


def get_resnet_training_deployment(ranking: DeploymentRanking,
                                   scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    resnet_training_gpu_function_image = FunctionImage(image=images.resnet50_training_gpu_manifest)

    resnet_training_cpu_function_image = FunctionImage(image=images.resnet50_training_cpu_manifest)

    resnet_training_function = Function(name=images.resnet50_training_function,
                                        fn_images=[resnet_training_gpu_function_image,
                                                   resnet_training_cpu_function_image])

    
    resnet_training_gpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="800Mi")
    data = storage.resnet_train_bucket_item.name

    data_storage_labels = {
        'data.skippy.io/receives-from-storage': '58M',
        'data.skippy.io/sends-to-storage': '103M',
        'data.skippy.io/receives-from-storage/path': f'{storage.resnet_train_bucket}/{data}',
        'data.skippy.io/sends-to-storage/path': f'{storage.resnet_train_bucket}/updated_model'
    }

    resnet_training_gpu_function = FunctionContainer(
        resnet_training_gpu_function_image,
        resource_config=resnet_training_gpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '2',
                'device.edgerun.io/accelerator': 'GPU',
                'device.edgerun.io/vram': '2000', }
    )

    resnet_training_gpu_function.labels.update(data_storage_labels)

    resnet_training_cpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="1Gi")
    resnet_training_cpu_function = FunctionContainer(
        resnet_training_cpu_function_image,
        resource_config=resnet_training_cpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '2'})

    resnet_training_cpu_function.labels.update(data_storage_labels)

    deployment = FunctionDeployment(
        resnet_training_function,
        [resnet_training_gpu_function, resnet_training_cpu_function],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_tf_gpu_deployment(ranking: DeploymentRanking, scaling_config: ScalingConfiguration = None):
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    tf_gpu_function_image = FunctionImage(image=images.tf_gpu_manifest)
    tf_gpu_function = Function(
        name=images.tf_gpu_function,
        fn_images=[tf_gpu_function_image]
    )

    
    tf_gpu_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="300Mi")
    tf_gpu_function_container = FunctionContainer(
        tf_gpu_function_image,
        resource_config=tf_gpu_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '3', 'device.edgerun.io/accelerator': 'GPU',
                'device.edgerun.io/vram': '2000', })

    deployment = FunctionDeployment(
        tf_gpu_function,
        [tf_gpu_function_container],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_pi_deployment(ranking: DeploymentRanking, scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    pi_function_image = FunctionImage(image=images.pi_manifest)
    pi_function = Function(name=images.pi_function, fn_images=[pi_function_image])

    
    pi_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="100Mi")

    pi_function_container = FunctionContainer(
        pi_function_image,
        resource_config=pi_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1'})

    deployment = FunctionDeployment(
        pi_function,
        [pi_function_container],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_fio_deployment(ranking: DeploymentRanking, scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    fio_function_image = FunctionImage(image=images.fio_manifest)
    fio_function = Function(name=images.fio_function, fn_images=[fio_function_image])

    
    fio_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m", memory="200Mi")

    fio_function_container = FunctionContainer(
        fio_function_image,
        resource_config=fio_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1'})

    deployment = FunctionDeployment(
        fio_function,
        [fio_function_container],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def get_resnet_preprocessing_deployment(ranking: DeploymentRanking, scaling_config: ScalingConfiguration = None):
    
    """
    函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：ranking：镜像/容器部署优先级排序。；scaling_config：函数伸缩策略配置。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    resnet_preprocessing_function_image = FunctionImage(image=images.resnet50_preprocessing_manifest)
    resnet_preprocessing_function = Function(name=images.resnet50_preprocessing_function,
                                             fn_images=[resnet_preprocessing_function_image])

    
    data = storage.resnet_pre_bucket_item.name

    data_storage_labels = {
        'data.skippy.io/receives-from-storage': '14M',
        'data.skippy.io/sends-to-storage': '14M',
        'data.skippy.io/receives-from-storage/path': f'{storage.resnet_pre_bucket}/{data}',
        'data.skippy.io/sends-to-storage/path': f'{storage.resnet_pre_bucket}/preprocessed'
    }

    resnet_preprocessing_function_requests = KubernetesResourceConfiguration.create_from_str(cpu="1000m",
                                                                                             memory="100Mi")

    resnet_preprocessing_function_container = FunctionContainer(
        fn_image=resnet_preprocessing_function_image,
        resource_config=resnet_preprocessing_function_requests,
        labels={'watchdog': 'http', 'workers': '4', 'cluster': '1'}
    )

    resnet_preprocessing_function.labels.update(data_storage_labels)

    deployment = FunctionDeployment(
        resnet_preprocessing_function,
        [resnet_preprocessing_function_container],
        ScalingConfiguration() if scaling_config is None else scaling_config,
        ranking
    )

    return deployment


def create_all_deployments(fet_oracle: FetOracle, resource_oracle: ResourceOracle,
                           deployment_rankings: DeploymentSettings = None) -> Dict[str, FunctionDeployment]:
    """
    函数作用：创建指定业务对象，并填充后续仿真流程需要的关键字段。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。；resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。；deployment_rankings：函数部署优先级配置集合，决定每类函数优先选择哪些镜像。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    if deployment_rankings is None:
        deployment_rankings = DeploymentSettings()
    return {
        images.resnet50_inference_function: get_resnet50_inference_deployment(
            deployment_rankings.resnet_inference_ranking),
        images.resnet50_training_function: get_resnet_training_deployment(deployment_rankings.resnet_training_ranking),
        images.mobilenet_inference_function: get_mobilenet_inference_deployment(
            deployment_rankings.mobilenet_inference_ranking),
        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
        # 业务说明：这里处理资源请求、资源占用或资源利用率统计。
        images.speech_inference_function: get_speech_inference_deployment(deployment_rankings.speech_inference_ranking),
        images.resnet50_preprocessing_function: get_resnet_preprocessing_deployment(
            deployment_rankings.resnet_preprocessing_ranking)
    }
