"""
文件作用：Raith21 存储抽象，定义实验中对象存储或数据源在拓扑中的标识。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

from ether.util import parse_size_string
from skippy.core.storage import DataItem

# 字段说明：resnet_train_bucket：对象存储桶标识，用于组织函数模型或输入数据。
resnet_train_bucket = 'bucket_resnet50_train'
# 字段说明：resnet_pre_bucket：对象存储桶标识，用于组织函数模型或输入数据。
resnet_pre_bucket = 'bucket_resnet50_pre'
# 字段说明：resnet_model_bucket：对象存储桶标识，用于组织函数模型或输入数据。
resnet_model_bucket = 'bucket_resnet50_model'
# 字段说明：speech_bucket：对象存储桶标识，用于组织函数模型或输入数据。
speech_bucket = 'bucket_speech'
# 字段说明：mobilenet_bucket：对象存储桶标识，用于组织函数模型或输入数据。
mobilenet_bucket = 'mobilenet_bucket'

# 字段说明：resnet_train_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
resnet_train_bucket_item = DataItem(resnet_train_bucket, 'raw_data', parse_size_string('58M'))
# 字段说明：resnet_pre_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
resnet_pre_bucket_item = DataItem(resnet_pre_bucket, 'raw_data', parse_size_string('14M'))
# 字段说明：resnet_model_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
resnet_model_bucket_item = DataItem(resnet_model_bucket, 'model', parse_size_string('103M'))
# 字段说明：speech_model_tflite_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
speech_model_tflite_bucket_item = DataItem(speech_bucket, 'model_tflite', parse_size_string('48M'))
# 字段说明：speech_model_gpu_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
speech_model_gpu_bucket_item = DataItem(speech_bucket, 'model_gpu', parse_size_string('188M'))
# 字段说明：mobilenet_model_tflite_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
mobilenet_model_tflite_bucket_item = DataItem(mobilenet_bucket, 'model_tflite', parse_size_string('4M'))
# 字段说明：mobilenet_model_tpu_bucket_item：对象存储中的模型或数据项，用于模拟函数启动或执行时的数据依赖。
mobilenet_model_tpu_bucket_item = DataItem(mobilenet_bucket, 'model_tpu', parse_size_string('4M'))

# 字段说明：bucket_names：表示 bucket、names，在当前业务流程中作为输入参数、状态字段或计算结果使用。
bucket_names = [
    resnet_model_bucket,
    resnet_train_bucket,
    resnet_pre_bucket,
    mobilenet_bucket,
    speech_bucket
]

# 字段说明：data_items：表示 data、items，在当前业务流程中作为输入参数、状态字段或计算结果使用。
data_items = [
    resnet_train_bucket_item,
    resnet_pre_bucket_item,
    resnet_model_bucket_item,
    speech_model_gpu_bucket_item,
    speech_model_tflite_bucket_item,
    mobilenet_model_tpu_bucket_item,
    mobilenet_model_tflite_bucket_item
]
