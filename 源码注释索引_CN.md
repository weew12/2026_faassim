# 源码注释索引（按文件）

下表列出每个 Python 文件的职责和其中包含的主要类/函数，便于快速定位。

## `ext/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `ext/raith21/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `ext/raith21/benchmark/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `ext/raith21/benchmark/constant.py`

恒定工作负载 Benchmark，按实验配置选择函数组合、部署函数并持续产生固定强度请求。

类：ConstantBenchmark

## `ext/raith21/calculations.py`

设备集合统计与异构度计算工具，用于衡量生成设备与需求向量之间的属性覆盖和差异。

函数：count_attribute、get_gpu_model_count、calculate_requirements、calculate_heterogeneity

## `ext/raith21/characterization.py`

Raith21 函数画像装配入口，将执行时间 Oracle 和资源 Oracle 组合成 FunctionCharacterization。

函数：get_raith21_function_characterizations

## `ext/raith21/deployments.py`

Raith21 函数部署定义文件，创建 ResNet、MobileNet、Speech、TensorFlow、Pi、Fio 等函数部署和镜像排序。

类：DeploymentSettings

函数：get_resnet50_inference_deployment、get_speech_inference_deployment、get_mobilenet_inference_deployment、get_resnet_training_deployment、get_tf_gpu_deployment、get_pi_deployment、get_fio_deployment、get_resnet_preprocessing_deployment、create_all_deployments

## `ext/raith21/device.py`

Raith21 设备抽象文件，将随机生成或真实设备参数封装为 Device/GpuDevice，并转换为调度标签。

类：ArchProperties、Device、GpuDevice

## `ext/raith21/etherdevices.py`

Raith21 设备到 Ether 节点的转换文件，定义 Raspberry Pi、Jetson、Xeon、Coral 等典型边缘/云节点的资源参数。

函数：create_rockpi、create_rpi4_node、create_coral、create_xeongpu、create_xeoncpu、create_nano、create_nx、create_node_from_device、create_aarch64_gpu、convert_to_ether_nodes、create_device_from_node、convert_to_devices

## `ext/raith21/fet.py`

Raith21 函数执行时间画像数据，保存不同函数在不同设备上的平均或分布式 FET 估计。

## `ext/raith21/functionsim.py`

Raith21 函数执行模拟器，基于函数画像和资源 Oracle 模拟 HTTP 函数队列、AI 推理 setup、资源占用和干扰退化。

类：PythonHTTPSimulator、PythonHttpSimulatorFactory、FunctionCall、InterferenceAwarePythonHttpSimulatorFactory、AIPythonHTTPSimulatorFactory、AIPythonHTTPSimulator、InterferenceAwarePythonHttpSimulator

函数：linear_queue_fet_increase

## `ext/raith21/generator.py`

异构设备生成器，按架构和属性概率生成设备集合，用于资源规划和大规模仿真实验。

类：GeneratorSettings

函数：xeon_reqs、create_generator、create_t_setting、create_settings、create_and_save_settings、save_setting、choose_attribute_settings、process_arches、filter_invalid_settings、generate_settings、generate_probabilities、generate_arch_probs、random_network_throughput、random_ram_size、random_cpu_cores、create_tuples、random_arch、random_bin、random_connection、random_location、random_cpu、random_accelerator、random_gpu_model、random_disk、get_property_with_probs、generate_devices_with_settings、generate_devices、main、generate_settings_main

## `ext/raith21/generators/__init__.py`

Raith21 设备生成配置文件，定义 __init__ 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/cloudcpu.py`

Raith21 设备生成配置文件，定义 cloudcpu 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/cloudgpu.py`

Raith21 设备生成配置文件，定义 cloudgpu 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/edgecloudlet.py`

Raith21 设备生成配置文件，定义 edgecloudlet 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/edgegpu.py`

Raith21 设备生成配置文件，定义 edgegpu 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/edgesbc.py`

Raith21 设备生成配置文件，定义 edgesbc 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/edgetpu.py`

Raith21 设备生成配置文件，定义 edgetpu 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/generate.py`

Raith21 设备生成配置文件，定义 generate 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

函数：count_devices、counter_to_csv、format_device、convert_to_dict、main

## `ext/raith21/generators/hybridbalanced.py`

Raith21 设备生成配置文件，定义 hybridbalanced 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/generators/hybridbalanced_jetson.py`

Raith21 设备生成配置文件，定义 hybridbalanced_jetson 场景下不同架构和设备属性的概率分布，用于生成可复现的异构节点集合。

## `ext/raith21/images.py`

源码模块，包含 0 个类和 0 个顶层函数，承担 images 相关的仿真支撑逻辑。

## `ext/raith21/loader.py`

模型文件下载与加载辅助逻辑，处理性能退化模型等外部文件的获取和反序列化。

函数：load_model、download_with_progress

## `ext/raith21/main.py`

Raith21 扩展实验入口，装配拓扑、Benchmark、调度策略和模拟器工厂后启动实验。

## `ext/raith21/model.py`

Raith21 扩展实验的设备属性与需求模型，定义架构、位置、磁盘、加速器、连接方式、GPU/CPU 型号和资源需求枚举。

类：Bins、Location、Disk、Accelerator、Connection、Arch、GpuModel、CpuModel、Requirements

## `ext/raith21/oracles.py`

Raith21 专用 Oracle，读取论文实验中的函数执行时间和资源画像，在给定节点上采样执行时延与资源向量。

类：Raith21FetOracle、Raith21ResourceOracle

## `ext/raith21/predicates.py`

Skippy 调度谓词扩展，判断节点是否满足内存、架构、加速器、TPU/GPU 独占等硬约束。

类：HasEnoughRamPredicate、CanRunPred、NodeHasAcceleratorPred、NodeHasFreeTpu、NodeHasFreeGpu

## `ext/raith21/priorities.py`

Skippy 调度优先级扩展，根据能力匹配、预计执行时间和资源竞争情况为候选节点打分。

类：CapabilityMatchingPriority、ExecutionTimePriority、ContentionPriority

## `ext/raith21/resourcemonitor.py`

Raith21 专用资源监控进程，周期读取资源状态并写入资源窗口指标。

类：Raith21ResourceMonitor

## `ext/raith21/resources.py`

Raith21 资源画像数据，保存不同函数在不同设备上的 CPU、内存、GPU、网络、块 I/O 使用量。

## `ext/raith21/storage.py`

Raith21 存储抽象，定义实验中对象存储或数据源在拓扑中的标识。

## `ext/raith21/topology.py`

Raith21 拓扑构造文件，生成云、城市感知、异构边缘集群等实验拓扑，并组合 Ether 节点、链路和网络单元。

类：XeonCloudlet、FasterMobileConnection、HeterogeneousUrbanSensingScenario

函数：all_internet_topology、urban_sensing_topology、parts

## `ext/raith21/util/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `ext/raith21/util/ga.py`

源码模块，包含 0 个类和 2 个顶层函数，承担 ga 相关的仿真支撑逻辑。

函数：get_predicates、get_priorities

## `ext/raith21/util/predicates.py`

源码模块，包含 0 个类和 1 个顶层函数，承担 predicates 相关的仿真支撑逻辑。

函数：get_predicates

## `ext/raith21/util/skippy.py`

源码模块，包含 0 个类和 2 个顶层函数，承担 skippy 相关的仿真支撑逻辑。

函数：get_predicates、get_priorities

## `ext/raith21/util/vanilla.py`

源码模块，包含 0 个类和 2 个顶层函数，承担 vanilla 相关的仿真支撑逻辑。

函数：get_predicates、get_priorities

## `ext/raith21/utils.py`

Raith21 Benchmark 辅助函数，按实验 profile 快速创建 AI、混合、服务型函数部署集合。

函数：extract_model_type、create_ai_deployments、create_mixed_deployments、create_service_deployments、create_deployments_for_profile

## `notebooks/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `setup.py`

项目安装入口，声明 faas-sim 包元数据、依赖和可安装的 Python 包范围，供 pip / setuptools 构建使用。

## `sim/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `sim/benchmark.py`

通用 Benchmark 基类，描述实验如何注册镜像、部署函数、启动请求生成器，并在仿真时间内维持工作负载。

类：Benchmark、BenchmarkBase、DegradationBenchmarkBase

函数：get_model_file、set_degradation

## `sim/core.py`

仿真运行环境和节点状态文件，集中保存 SimPy 环境、拓扑、FaaS 系统、调度器、资源状态、指标记录器和节点运行时状态。

类：NodeState、SimulationTimeoutError、Environment

函数：timeout_listener

## `sim/degradation.py`

性能退化模型输入构造文件，将当前并发函数的资源向量汇总成固定长度特征，供机器学习退化模型预测使用。

函数：create_degradation_model_input

## `sim/docker.py`

容器镜像仓库和镜像拉取模拟，实现镜像元数据登记、按架构查找镜像，以及通过网络流下载镜像大小。

类：ImageProperties、ContainerRegistry

函数：split_image_name、pull

## `sim/faas/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `sim/faas/core.py`

FaaS 领域模型核心文件，定义函数、镜像、容器、副本、部署、请求/响应、资源配置、生命周期状态以及 FaaS 系统抽象接口。

类：FunctionState、Resources、FunctionResourceCharacterization、FunctionCharacterization、FunctionImage、DeploymentRanking、ResourceConfiguration、KubernetesResourceConfiguration、Function、FunctionContainer、ScalingConfiguration、FunctionDeployment、FunctionReplica、FunctionRequest、FunctionResponse、FaasSystem、LoadBalancer、RoundRobinLoadBalancer、FunctionSimulator、SimulatorFactory

函数：counter

## `sim/faas/scaling.py`

函数自动伸缩后台进程实现，包含 scale-to-zero idler、基于请求数的扩缩容、平均 RPS 扩缩容和队列长度扩缩容逻辑。

类：FaasRequestScaler、AverageFaasRequestScaler、AverageQueueFaasRequestScaler

函数：faas_idler

## `sim/faas/system.py`

默认 FaaS 平台实现文件，负责函数部署、副本创建、调度队列、调用转发、扩缩容、挂起与删除等完整业务流程。

类：DefaultFaasSystem

函数：simulate_function_start、simulate_data_download、simulate_data_upload、simulate_function_invocation

## `sim/faas/watchdogs.py`

OpenFaaS watchdog 执行模型抽象，模拟 Fork 模式和 HTTP worker 队列模式下函数请求如何进入用户处理逻辑。

类：Watchdog、ForkingWatchdog、HTTPWatchdog

## `sim/faassim.py`

仿真启动与装配入口，完成环境初始化、容器仓库创建、调度器创建、FaaS 系统挂载和 Benchmark 执行。

类：BadPlacementException、Simulation、DummySimulator、DockerDeploySimMixin、ModeledExecutionSimMixin、SimpleFunctionSimulator、SimpleSimulatorFactory

## `sim/hpa.py`

Kubernetes HPA 风格自动伸缩器，周期读取平均 CPU 利用率并根据目标利用率调整函数副本数。

类：HorizontalPodAutoscaler

## `sim/logging.py`

轻量运行日志抽象，统一墙上时钟/仿真时钟记录格式，为运行过程输出结构化 Record。

类：Clock、WallClock、Record、SimulatedClock、RuntimeLogger、NullLogger、PrintLogger

## `sim/metrics.py`

仿真指标记录中心，将部署、调度、调用、资源、网络、生命周期等事件写成结构化记录，便于导出 DataFrame 分析。

类：Metrics

## `sim/net.py`

网络安全包装逻辑，在 Ether flow 基础上增加低带宽异常判断，避免资源受限链路被静默使用。

类：LowBandwidthException

函数：SafeFlow

## `sim/oracle/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `sim/oracle/data/__init__.py`

包初始化文件，声明该目录是 Python 包，并集中暴露或承载同级模块的导入入口。

## `sim/oracle/data/distributions.py`

统计分布工具文件，封装离散分布采样逻辑，供经验型 Oracle 从历史观测值中抽样。

## `sim/oracle/oracle.py`

性能与资源 Oracle 抽象集合，封装启动时间、执行时间、带宽、成本、资源利用率和拟合分布采样等估计接口。

类：Oracle、EmpiricalOracle、StartupTimeOracle、ExecutionTimeOracle、BandwidthUsageOracle、CostOracle、ResourceUtilizationOracle、FittedStartupTimeOracle、HackedFittedStartupTimeOracle、FittedExecutionTimeOracle、FetOracle、ResourceOracle

## `sim/requestgen.py`

请求到达模型和工作负载生成器，提供固定、正弦、随机游走、指数分布和预录制到达间隔等请求模式。

函数：constant_rps_profile、sine_rps_profile、randomwalk_rps_profile、static_arrival_profile、expovariate_arrival_profile、pre_recorded_profile、function_trigger、run_arrival_profile、save_requests

## `sim/resource.py`

资源状态和资源监控实现，记录函数副本在节点上的 CPU、内存、网络、磁盘等资源占用，并按窗口汇总指标。

类：ResourceUtilization、NodeResourceUtilization、ResourceState、ResourceWindow、MetricsServer、ResourceMonitor

## `sim/skippy.py`

faas-sim 与 Skippy 调度器的适配层，将 Ether 节点和 FunctionReplica 转换为调度器可识别的节点/Pod 视图。

类：SimulationClusterContext

函数：to_skippy_node、create_function_pod

## `sim/topology.py`

Ether 拓扑包装层，提供容器仓库节点初始化、节点查找、路由查询和按需带宽图访问。

类：Topology、LazyBandwidthGraph


## `skippy/__init__.py`

内置 Skippy 调度子包入口，说明其替换外部 `edgerun-skippy-core` 依赖后的导入兼容关系。

## `skippy/core/model.py`

Skippy 调度领域模型，定义镜像状态、容器资源请求、Pod、节点容量与调度结果。

类：ImageState、ResourceRequirements、Container、PodSpec、Pod、Capacity、Node、SchedulingResult

## `skippy/core/clustercontext.py`

Skippy 集群上下文抽象，维护节点列表、镜像状态、节点剩余资源、带宽图和对象存储索引。

类：ClusterContext

函数/方法重点：get_node、place_pod_on_node、remove_pod_from_node、remove_pod_images_from_node、get_image_state、get_dl_bandwidth、get_image_sizes

## `skippy/core/predicates.py`

Skippy 调度过滤逻辑，判断 Pod 是否满足节点资源与标签约束。

类：Predicate、CombinedPredicate、PodFitsResourcesPred、NonCriticalPreds、EssentialPreds、GeneralPreds、CheckNodeLabelPresencePred

## `skippy/core/priorities.py`

Skippy 调度打分逻辑，综合资源均衡、镜像本地性、数据本地性、边缘位置和硬件能力进行节点评分。

类：Priority、EqualPriority、ImageLocalityPriority、ResourcePriority、BalancedResourcePriority、LocalityTypePriority、CapabilityPriority、LocalityPriority、LatencyAwareImageLocalityPriority、DataLocalityPriority

函数：_scale_scores、_scale_scores_inverse

## `skippy/core/scheduler.py`

Skippy 调度器主流程，串联谓词过滤、优先级打分、最高分节点选择和调度状态写回。

类：Scheduler

方法重点：schedule、passes_predicates、__num_feasible_nodes_to_find

## `skippy/core/storage.py`

对象存储位置索引，维护 bucket、对象和存储节点之间的关系，供数据本地性调度使用。

类：DataItem、StorageIndex

## `skippy/core/utils.py`

调度工具函数，提供镜像名规范化、容量字符串解析、计时器和递增计数器。

类：Timer

函数：normalize_image_name、parse_size_string、counter

## 内置 SimPy 子包注释索引

- `simpy/core.py`：事件队列、仿真时钟、事件调度、单步推进和 run 循环。
- `simpy/events.py`：Event、Timeout、Process、Condition 等事件与进程恢复机制。
- `simpy/resources/base.py`：共享资源 put/get 队列骨架。
- `simpy/resources/container.py`：连续容量资源。
- `simpy/resources/resource.py`：有限并发槽位、优先级和抢占式资源。
- `simpy/resources/store.py`：FIFO、优先级和过滤式对象队列。
- `simpy/rt.py` 与 `simpy/util.py`：实时环境与进程编排工具。
