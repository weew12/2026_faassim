"""
文件作用：源码模块，包含 0 个类和 0 个顶层函数，承担 images 相关的仿真支撑逻辑。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

# 字段说明：resnet50_inference_cpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
resnet50_inference_cpu_manifest = 'faas-workloads/resnet-inference-cpu'
# 字段说明：resnet50_inference_gpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
resnet50_inference_gpu_manifest = 'faas-workloads/resnet-inference-gpu'
# 字段说明：resnet50_inference_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
resnet50_inference_function = 'resnet50-inference'

# 字段说明：resnet50_training_gpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
resnet50_training_gpu_manifest = 'faas-workloads/resnet-training-gpu'
# 字段说明：resnet50_training_cpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
resnet50_training_cpu_manifest = 'faas-workloads/resnet-training-cpu'
# 字段说明：resnet50_training_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
resnet50_training_function = 'resnet50-training'

# 字段说明：speech_inference_tflite_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
speech_inference_tflite_manifest = 'faas-workloads/speech-inference-tflite'
# 字段说明：speech_inference_gpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
speech_inference_gpu_manifest = 'faas-workloads/speech-inference-gpu'
# 字段说明：speech_inference_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
speech_inference_function = 'speech-inference'

# 字段说明：mobilenet_inference_tflite_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
mobilenet_inference_tflite_manifest = 'faas-workloads/mobilenet-inference-tflite'
# 字段说明：mobilenet_inference_tpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
mobilenet_inference_tpu_manifest = 'faas-workloads/mobilenet-inference-tpu'
# 字段说明：mobilenet_inference_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
mobilenet_inference_function = 'mobilenet-inference'

# 字段说明：resnet50_preprocessing_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
resnet50_preprocessing_function = 'resnet50-preprocessing'
# 字段说明：resnet50_preprocessing_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
resnet50_preprocessing_manifest = 'faas-workloads/resnet-preprocessing'

# 字段说明：pi_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
pi_manifest = 'faas-workloads/python-pi'
# 字段说明：pi_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
pi_function = 'python-pi'

# 字段说明：fio_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
fio_manifest = 'faas-workloads/fio'
# 字段说明：fio_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
fio_function = 'fio'

# 字段说明：tf_gpu_manifest：函数镜像清单，保存该函数在不同架构或加速器版本下的容器镜像。
tf_gpu_manifest = 'faas-workloads/tf-gpu'
# 字段说明：tf_gpu_function：函数名称常量，用于创建 Function、Deployment 和请求目标。
tf_gpu_function = 'tf-gpu'
# 字段说明：all_ai_images：表示 all、ai、images，在当前业务流程中作为输入参数、状态字段或计算结果使用。
all_ai_images = [
    (resnet50_inference_cpu_manifest, '2000M', 'x86'),
    (resnet50_inference_cpu_manifest, '2000M', 'amd64'),
    (resnet50_inference_cpu_manifest, '700M', 'arm32v7'),
    (resnet50_inference_cpu_manifest, '700M', 'arm32'),
    (resnet50_inference_cpu_manifest, '700M', 'arm'),
    (resnet50_inference_cpu_manifest, '840M', 'aarch64'),
    (resnet50_inference_cpu_manifest, '840M', 'arm64'),

    (resnet50_inference_gpu_manifest, '2000M', 'x86'),
    (resnet50_inference_gpu_manifest, '2000M', 'amd64'),
    (resnet50_inference_gpu_manifest, '1000M', 'aarch64'),
    (resnet50_inference_gpu_manifest, '1000M', 'arm64'),

    (resnet50_training_gpu_manifest, '2000M', 'x86'),
    (resnet50_training_gpu_manifest, '2000M', 'amd64'),
    (resnet50_training_gpu_manifest, '1000M', 'aarch64'),
    (resnet50_training_gpu_manifest, '1000M', 'arm64'),

    (resnet50_training_cpu_manifest, '2000M', 'amd64'),
    (resnet50_training_cpu_manifest, '2000M', 'x86'),

    (speech_inference_tflite_manifest, '108M', 'amd64'),
    (speech_inference_tflite_manifest, '108M', 'x86'),
    (speech_inference_tflite_manifest, '328M', 'arm32v7'),
    (speech_inference_tflite_manifest, '328M', 'arm32'),
    (speech_inference_tflite_manifest, '328M', 'arm'),
    (speech_inference_tflite_manifest, '400M', 'arm64'),
    (speech_inference_tflite_manifest, '400M', 'aarch64'),

    (speech_inference_gpu_manifest, '1600M', 'amd64'),
    (speech_inference_gpu_manifest, '1600M', 'x86'),
    (speech_inference_gpu_manifest, '1300M', 'arm64'),
    (speech_inference_gpu_manifest, '1300M', 'aarch64'),

    (mobilenet_inference_tflite_manifest, '180M', 'amd64'),
    (mobilenet_inference_tflite_manifest, '180M', 'x86'),
    (mobilenet_inference_tflite_manifest, '160M', 'arm32v7'),
    (mobilenet_inference_tflite_manifest, '160M', 'arm32'),
    (mobilenet_inference_tflite_manifest, '160M', 'arm'),
    (mobilenet_inference_tflite_manifest, '173M', 'arm64'),
    (mobilenet_inference_tflite_manifest, '173M', 'aarch64'),

    (mobilenet_inference_tpu_manifest, '173M', 'arm64'),
    (mobilenet_inference_tpu_manifest, '173M', 'aarch64'),

    (pi_manifest, '88M', 'amd64'),
    (pi_manifest, '88M', 'x86'),
    (pi_manifest, '55M', 'arm32v7'),
    (pi_manifest, '55M', 'arm32'),
    (pi_manifest, '55M', 'arm'),
    (pi_manifest, '62M', 'arm64'),
    (pi_manifest, '62M', 'aarch64'),

    (fio_manifest, '24M', 'amd64'),
    (fio_manifest, '24M', 'x86'),
    (fio_manifest, '20M', 'arm32v7'),
    (fio_manifest, '20M', 'arm32'),
    (fio_manifest, '20M', 'arm'),
    (fio_manifest, '23M', 'arm64'),
    (fio_manifest, '23M', 'aarch64'),

    (tf_gpu_manifest, '4100M', 'amd64'),
    (tf_gpu_manifest, '4100M', 'x86'),
    (tf_gpu_manifest, '2240M', 'arm64'),
    (tf_gpu_manifest, '2240M', 'aarch64'),

    (resnet50_preprocessing_manifest, '4100M', 'x86'),
    (resnet50_preprocessing_manifest, '4100M', 'amd64'),
    (resnet50_preprocessing_manifest, '1370M', 'arm32v7'),
    (resnet50_preprocessing_manifest, '1370M', 'arm32'),
    (resnet50_preprocessing_manifest, '1370M', 'arm'),
    (resnet50_preprocessing_manifest, '1910M', 'arm64'),
    (resnet50_preprocessing_manifest, '1910M', 'aarch64')
]
