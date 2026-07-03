"""
文件作用：恒定工作负载 Benchmark，按实验配置选择函数组合、部署函数并持续产生固定强度请求。
主要类：ConstantBenchmark。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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
    类作用：恒定负载 Benchmark，按固定请求强度运行一组函数部署并收集结果。
    继承关系：BenchmarkBase。
    核心方法：__init__、settings、type、setup、setup_profile、set_mixed_profiles、set_ai_profiles、set_service_profiles、set_deployments。
    """
    def __init__(self, profile: str, duration: int, rps=200, model_folder=None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：duration、model_folder、profile、rps。
        参数：profile：实验 profile 名称或配置，用于选择函数集合和负载类型。；duration：实验持续时间。；rps：每秒请求数，用于控制请求生成强度。；model_folder：性能退化模型所在目录。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        all_images = images.all_ai_images
        # 字段说明：self.model_folder：性能退化模型文件所在目录。
        self.model_folder = model_folder
        # 字段说明：self.profile：实验 profile 名称或配置，用于选择函数集合和负载类型。
        self.profile = profile
        # 字段说明：self.rps：每秒请求数，用于控制请求生成强度。
        self.rps = rps
        # 字段说明：self.duration：Benchmark 持续的仿真时间长度。
        self.duration = duration
        fet_oracle = Raith21FetOracle(ai_execution_time_distributions)
        resource_oracle = Raith21ResourceOracle(ai_resources_per_node_image)

        deployments = create_deployments_for_profile(profile, fet_oracle, resource_oracle)

        super().__init__(all_images, list(deployments.values()), arrival_profiles=dict(), duration=duration)

    @property
    def settings(self):
        """
        函数作用：处理 settings 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return {
            'profile': self.profile,
            'rps': self.rps,
            'duration': self.duration
        }

    @property
    def type(self):
        """
        函数作用：处理 type 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return 'constant'

    def setup(self, env: Environment):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.set_deployments(env)
        self.setup_profile()
        if self.model_folder is not None:
            set_degradation(env, self.model_folder)
        super().setup(env)

    def setup_profile(self):
        """
        函数作用：按实验 profile 装配函数画像、部署集合和请求模式。
        关键流程：
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
        函数作用：更新对象内部状态或实验配置。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
        函数作用：更新对象内部状态或实验配置。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
        函数作用：更新对象内部状态或实验配置。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        self.arrival_profiles[images.pi_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))
        self.arrival_profiles[images.tf_gpu_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))
        
        self.arrival_profiles[images.fio_function] = \
            expovariate_arrival_profile(constant_rps_profile(self.rps))

    def set_deployments(self, env):
        """
        函数作用：更新对象内部状态或实验配置。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
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
