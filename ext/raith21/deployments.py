"""
Raith21 论文工作负载的函数部署定义。

本模块定义 ResNet、MobileNet、Speech、TensorFlow、Pi、Fio 和预处理函数的镜像、资源请求、标签、数据依赖、伸缩配置与镜像排序。
"""

from dataclasses import dataclass
from typing import Dict

from ext.raith21 import images, storage
from sim.faas import DeploymentRanking, FunctionDeployment, FunctionImage, \
    FunctionContainer, KubernetesResourceConfiguration, Function, ScalingConfiguration
from sim.oracle.oracle import ResourceOracle, FetOracle

default_resnet_inference_ranking = DeploymentRanking(
    [images.resnet50_inference_gpu_manifest, images.resnet50_inference_cpu_manifest])
default_speech_inference_ranking = DeploymentRanking(
    [images.speech_inference_tflite_manifest, images.speech_inference_gpu_manifest])
default_mobilenet_inference_ranking = DeploymentRanking(
    [images.mobilenet_inference_tpu_manifest, images.mobilenet_inference_tflite_manifest])
default_resnet_training_ranking = DeploymentRanking(
    [images.resnet50_training_gpu_manifest, images.resnet50_training_cpu_manifest])
default_pi_ranking = DeploymentRanking([images.pi_manifest])
default_fio_ranking = DeploymentRanking([images.fio_manifest])
default_tf_gpu_ranking = DeploymentRanking([images.tf_gpu_manifest])
default_resnet_preprocessing_ranking = DeploymentRanking([images.resnet50_preprocessing_manifest])


@dataclass
class DeploymentSettings:
    """
    函数镜像排序配置集合。

    为每类 Raith21 workload 保存 DeploymentRanking，使实验可以统一替换不同函数的镜像优先顺序。

    关键字段:
        resnet_inference_ranking: ResNet50 推理镜像排序。
        resnet_preprocessing_ranking: ResNet50 预处理镜像排序。
        speech_inference_ranking: 语音推理镜像排序。
        mobilenet_inference_ranking: MobileNet 推理镜像排序。
        resnet_training_ranking: ResNet50 训练镜像排序。
        tf_gpu_ranking: TensorFlow GPU 函数镜像排序。
        pi_ranking: Pi 计算函数镜像排序。
        fio_ranking: Fio I/O 函数镜像排序。
    """
    resnet_inference_ranking: DeploymentRanking = default_resnet_inference_ranking
    resnet_preprocessing_ranking: DeploymentRanking = default_resnet_preprocessing_ranking
    speech_inference_ranking: DeploymentRanking = default_speech_inference_ranking
    mobilenet_inference_ranking: DeploymentRanking = default_mobilenet_inference_ranking
    resnet_training_ranking: DeploymentRanking = default_resnet_training_ranking
    tf_gpu_ranking: DeploymentRanking = default_tf_gpu_ranking
    pi_ranking: DeploymentRanking = default_pi_ranking
    fio_ranking: DeploymentRanking = default_fio_ranking


def get_resnet50_inference_deployment(ranking: DeploymentRanking,
                                      scaling_config: ScalingConfiguration = None) -> FunctionDeployment:
    
    """
    创建 ResNet50 推理部署，提供 GPU/CPU 两种镜像，并声明模型输入数据与显存需求。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建语音推理部署，提供 GPU 与 TFLite 镜像，并为不同模型配置独立数据对象。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建 MobileNet 推理部署，提供 TPU 与 TFLite 镜像及对应加速器标签。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建 ResNet50 训练部署，提供 GPU/CPU 镜像，并声明训练数据读取与模型写回路径。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建 TensorFlow GPU 服务部署，并声明 GPU 与显存需求。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        计算、查询或构造得到的结果。
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
    创建 CPU 密集型 Pi 计算服务部署。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建磁盘 I/O 密集型 Fio 服务部署。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        FunctionDeployment。
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
    创建 ResNet50 数据预处理部署，并声明输入数据与预处理结果的存储路径。

    参数:
        ranking: 函数镜像部署排序。 类型：DeploymentRanking。
        scaling_config: 函数伸缩配置。 类型：ScalingConfiguration。

    返回:
        计算、查询或构造得到的结果。
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
    按 DeploymentSettings 创建全部 Raith21 函数部署，并绑定 FET/资源 Oracle。

    参数:
        fet_oracle: 函数执行时间 Oracle。 类型：FetOracle。
        resource_oracle: 函数资源画像 Oracle。 类型：ResourceOracle。
        deployment_rankings: 用于控制当前生成、筛选或配置过程的参数。 类型：DeploymentSettings。

    返回:
        Dict[str, FunctionDeployment]。
    """
    if deployment_rankings is None:
        deployment_rankings = DeploymentSettings()
    return {
        images.resnet50_inference_function: get_resnet50_inference_deployment(
            deployment_rankings.resnet_inference_ranking),
        images.resnet50_training_function: get_resnet_training_deployment(deployment_rankings.resnet_training_ranking),
        images.mobilenet_inference_function: get_mobilenet_inference_deployment(
            deployment_rankings.mobilenet_inference_ranking),
        images.speech_inference_function: get_speech_inference_deployment(deployment_rankings.speech_inference_ranking),
        images.resnet50_preprocessing_function: get_resnet_preprocessing_deployment(
            deployment_rankings.resnet_preprocessing_ranking)
    }
