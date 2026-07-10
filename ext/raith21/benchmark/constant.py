"""
固定到达率的 Raith21 Benchmark。

本模块根据实验类型创建函数部署与固定请求到达模型，并在 setup 阶段选择 AI、混合或服务型 workload。
"""

from ext.raith21 import images
from ext.raith21.fet import ai_execution_time_distributions
from ext.raith21.oracles import Raith21FetOracle, Raith21ResourceOracle
from ext.raith21.resources import ai_resources_per_node_image
from ext.raith21.utils import create_deployments_for_profile
from sim.benchmark import BenchmarkBase, set_degradation
from sim.core import Environment
from sim.requestgen import expovariate_arrival_profile, constant_rps_profile


class ConstantBenchmark(BenchmarkBase):

    """
    固定请求速率 Benchmark。

    根据 profile 类型构造部署和固定 RPS 到达间隔，为论文策略比较提供稳定 workload。

    关键字段:
        model_folder: 性能退化模型目录；为空时不加载退化模型。
        profile: 工作负载类型，可选 service、ai 或 mixed。
        rps: 固定请求速率。
        duration: Benchmark 持续时间。
    """
    def __init__(self, profile: str, duration: int, rps=200, model_folder=None):
        """
        初始化 ConstantBenchmark。

        建立字段：model_folder、profile、rps、duration。

        参数:
            profile: 工作负载类型，可选 service、ai 或 mixed。 类型：str。
            duration: Benchmark 仿真时长。 类型：int。
            rps: 固定请求速率。
            model_folder: 性能退化模型目录。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        all_images = images.all_ai_images
        self.model_folder = model_folder
        self.profile = profile
        self.rps = rps
        self.duration = duration
        fet_oracle = Raith21FetOracle(ai_execution_time_distributions)
        resource_oracle = Raith21ResourceOracle(ai_resources_per_node_image)

        deployments = create_deployments_for_profile(profile, fet_oracle, resource_oracle)

        super().__init__(all_images, list(deployments.values()), arrival_profiles=dict(), duration=duration)

    @property
    def settings(self):
        """
        返回可序列化的 profile、RPS 和持续时间配置。

        返回:
            计算、查询或构造得到的结果。
        """
        return {
            'profile': self.profile,
            'rps': self.rps,
            'duration': self.duration
        }

    @property
    def type(self):
        """
        返回 Benchmark 类型标识 constant。

        返回:
            计算、查询或构造得到的结果。
        """
        return 'constant'

    def setup(self, env: Environment):
        """
        根据拓扑调整部署伸缩参数、建立到达模型，并可选加载性能退化模型。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.set_deployments(env)
        self.setup_profile()
        if self.model_folder is not None:
            set_degradation(env, self.model_folder)
        super().setup(env)

    def setup_profile(self):
        """
        根据 service、ai 或 mixed profile 选择请求到达模型。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        if self.profile == 'service':
            self.set_service_profiles()
        elif self.profile == 'ai':
            self.set_ai_profiles()
        elif self.profile == 'mixed':
            self.set_mixed_profiles()
        else:
            raise AttributeError(f'unknown profile: {self.profile}')

    def set_mixed_profiles(self):
        """
        为混合 workload 配置推理、训练和预处理请求到达率。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.arrival_profiles[images.resnet50_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.mobilenet_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.speech_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.resnet50_training_function] = \
            expovariate_arrival_profile(constant_rps_profile(0.1))

        self.arrival_profiles[images.resnet50_preprocessing_function] = \
            expovariate_arrival_profile(constant_rps_profile(1))

    def set_ai_profiles(self):

        """
        为全部 AI workload 配置请求到达率。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.arrival_profiles[images.resnet50_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.mobilenet_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.speech_inference_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

        self.arrival_profiles[images.resnet50_training_function] = \
            expovariate_arrival_profile(constant_rps_profile(0.1))

        self.arrival_profiles[images.resnet50_preprocessing_function] = \
            expovariate_arrival_profile(constant_rps_profile(1))

    def set_service_profiles(self):
        """
        为 Pi、TensorFlow GPU 和 Fio 服务配置请求到达率。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.arrival_profiles[images.pi_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))
        self.arrival_profiles[images.tf_gpu_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))
        
        self.arrival_profiles[images.fio_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

    def set_deployments(self, env):
        """
        根据拓扑节点数设置各函数的副本上限、伸缩步长和 RPS 阈值。

        参数:
            env: faas-sim 仿真环境。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        deployments = self.deployments_per_name
        for deployment in deployments.values():
            deployment.scale_min = 5
            deployment.target_average_utilization = 0.5
        no_of_devices = len(env.topology.get_nodes())

        deployments[images.resnet50_inference_function].rps_threshold = 100
        deployments[images.resnet50_inference_function].scale_max = int(0.7 * no_of_devices)
        deployments[images.resnet50_inference_function].scale_factor = int(0.05 * no_of_devices)
        deployments[images.resnet50_inference_function].rps_threshold_duration = 10

        deployments[images.mobilenet_inference_function].rps_threshold = 70
        deployments[images.mobilenet_inference_function].scale_max = int(0.25 * no_of_devices)
        deployments[images.mobilenet_inference_function].scale_factor = 5
        deployments[images.mobilenet_inference_function].rps_threshold_duration = 10

        deployments[images.speech_inference_function].rps_threshold = 40
        deployments[images.speech_inference_function].scale_max = int(0.25 * no_of_devices)
        deployments[images.speech_inference_function].scale_factor = 5
        deployments[images.speech_inference_function].rps_threshold_duration = 15

        deployments[images.resnet50_preprocessing_function].rps_threshold = 40
        deployments[images.resnet50_preprocessing_function].scale_max = no_of_devices / 4
        deployments[images.resnet50_preprocessing_function].scale_factor = 1
        deployments[images.resnet50_preprocessing_function].rps_threshold_duration = 15

        deployments[images.resnet50_training_function].rps_threshold = 40
        deployments[images.resnet50_training_function].scale_max = no_of_devices / 2
        deployments[images.resnet50_training_function].scale_factor = 1
        deployments[images.resnet50_training_function].rps_threshold_duration = 15
