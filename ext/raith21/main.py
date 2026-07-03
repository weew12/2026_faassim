"""
文件作用：Raith21 扩展实验入口，装配拓扑、Benchmark、调度策略和模拟器工厂后启动实验。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""


# coding: utf-8
import logging
import random

import numpy as np
from skippy.core.scheduler import Scheduler
from skippy.core.storage import StorageIndex

from ext.raith21 import images
from ext.raith21.benchmark.constant import ConstantBenchmark
from ext.raith21.characterization import get_raith21_function_characterizations
from ext.raith21.deployments import create_all_deployments
from ext.raith21.etherdevices import convert_to_ether_nodes
from ext.raith21.fet import ai_execution_time_distributions
from ext.raith21.functionsim import AIPythonHTTPSimulatorFactory
from ext.raith21.generator import generate_devices
from ext.raith21.generators.cloudcpu import cloudcpu_settings
from ext.raith21.oracles import Raith21ResourceOracle, Raith21FetOracle
from ext.raith21.predicates import CanRunPred, NodeHasAcceleratorPred, NodeHasFreeGpu, NodeHasFreeTpu
from ext.raith21.resources import ai_resources_per_node_image
from ext.raith21.topology import urban_sensing_topology
from ext.raith21.util import vanilla
from sim.core import Environment
from sim.docker import ContainerRegistry
from sim.faas.system import DefaultFaasSystem
from sim.faassim import Simulation
from sim.logging import SimulatedClock, RuntimeLogger
from sim.metrics import Metrics
from sim.skippy import SimulationClusterContext

np.random.seed(1234)
random.seed(1234)
logging.basicConfig(level=logging.INFO)

# 字段说明：num_devices：表示 num、devices，在当前业务流程中作为输入参数、状态字段或计算结果使用。
num_devices = 100
# 字段说明：devices：设备对象列表，用于拓扑生成、异构度统计或节点转换。
devices = generate_devices(num_devices, cloudcpu_settings)
# 字段说明：ether_nodes：表示 ether、nodes，在当前业务流程中作为输入参数、状态字段或计算结果使用。
ether_nodes = convert_to_ether_nodes(devices)

# 字段说明：fet_oracle：函数执行时间 Oracle，用于按节点采样 FET。
fet_oracle = Raith21FetOracle(ai_execution_time_distributions)
# 字段说明：resource_oracle：资源画像 Oracle，用于按节点读取函数资源向量。
resource_oracle = Raith21ResourceOracle(ai_resources_per_node_image)

# 字段说明：deployments：函数部署集合，描述本次实验要上线的函数及其配置。
deployments = list(create_all_deployments(fet_oracle, resource_oracle).values())
# 字段说明：function_images：表示 function、images，在当前业务流程中作为输入参数、状态字段或计算结果使用。
function_images = images.all_ai_images

# 字段说明：predicates：表示 predicates，在当前业务流程中作为输入参数、状态字段或计算结果使用。
predicates = []
predicates.extend(Scheduler.default_predicates)
predicates.extend([
    CanRunPred(fet_oracle, resource_oracle),
    NodeHasAcceleratorPred(),
    NodeHasFreeGpu(),
    NodeHasFreeTpu()
])

# 字段说明：priorities：表示 priorities，在当前业务流程中作为输入参数、状态字段或计算结果使用。
priorities = vanilla.get_priorities()

# 字段说明：sched_params：表示 sched、params，在当前业务流程中作为输入参数、状态字段或计算结果使用。
sched_params = {
    'percentage_of_nodes_to_score': 100,
    'priorities': priorities,
    'predicates': predicates
}


# 字段说明：benchmark：实验场景对象，定义镜像注册、函数部署和请求生成逻辑。
benchmark = ConstantBenchmark('mixed', duration=200, rps=50)

# 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
# 字段说明：storage_index：存储节点索引，用于模拟函数输入/输出数据传输。
storage_index = StorageIndex()
# 字段说明：topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
topology = urban_sensing_topology(ether_nodes, storage_index)


# 字段说明：env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
env = Environment()

# 字段说明：env.simulator_factory：函数模拟器工厂，根据函数定义创建具体 FunctionSimulator。
env.simulator_factory = AIPythonHTTPSimulatorFactory(
    get_raith21_function_characterizations(resource_oracle, fet_oracle))
# 字段说明：env.metrics：结构化指标记录器。
env.metrics = Metrics(env, log=RuntimeLogger(SimulatedClock(env)))
# 字段说明：env.topology：Ether 拓扑对象，描述节点、链路、路由和容器仓库位置。
env.topology = topology
# 字段说明：env.faas：FaaS 系统实例，负责函数部署、调用、扩缩容和副本生命周期管理。
env.faas = DefaultFaasSystem(env, scale_by_requests=True)
# 字段说明：env.container_registry：容器镜像仓库，保存可拉取镜像及其大小、架构信息。
env.container_registry = ContainerRegistry()
# 字段说明：env.storage_index：存储节点索引，用于模拟函数输入/输出数据传输。
env.storage_index = storage_index
# 字段说明：env.cluster：调度上下文，向调度器暴露节点、资源和镜像缓存状态。
env.cluster = SimulationClusterContext(env)
# 字段说明：env.scheduler：函数副本调度器，决定副本放置到哪个节点。
env.scheduler = Scheduler(env.cluster, **sched_params)

# 字段说明：sim：表示 sim，在当前业务流程中作为输入参数、状态字段或计算结果使用。
sim = Simulation(env.topology, benchmark, env=env)
# 字段说明：result：表示 result，在当前业务流程中作为输入参数、状态字段或计算结果使用。
result = sim.run()

# 字段说明：dfs：表示 dfs，在当前业务流程中作为输入参数、状态字段或计算结果使用。
dfs = {
    "invocations_df": sim.env.metrics.extract_dataframe('invocations'),
    "scale_df": sim.env.metrics.extract_dataframe('scale'),
    "schedule_df": sim.env.metrics.extract_dataframe('schedule'),
    "replica_deployment_df": sim.env.metrics.extract_dataframe('replica_deployment'),
    "function_deployments_df": sim.env.metrics.extract_dataframe('function_deployments'),
    "function_deployment_df": sim.env.metrics.extract_dataframe('function_deployment'),
    "function_deployment_lifecycle_df": sim.env.metrics.extract_dataframe('function_deployment_lifecycle'),
    "functions_df": sim.env.metrics.extract_dataframe('functions'),
    "flow_df": sim.env.metrics.extract_dataframe('flow'),
    "network_df": sim.env.metrics.extract_dataframe('network'),
    "utilization_df": sim.env.metrics.extract_dataframe('utilization'),
    'fets_df': sim.env.metrics.extract_dataframe('fets')
}
print(len(dfs))
