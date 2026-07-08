"""
仿真结果分析示例。

本示例复用 ``examples.basic`` 的拓扑和 benchmark，并使用
``examples.custom_function_sim`` 中的自定义函数模拟器运行一次完整仿真。仿真结束后，
从 ``env.metrics`` 提取常见指标表，并计算一次简单的调用执行时间均值。

这个示例的重点不是实现新的调度器或工作负载，而是展示如何从一次 Simulation 中
读取 Metrics 数据并开始做后处理分析。
"""

import logging

import examples.basic.main as basic
from examples.custom_function_sim.main import CustomSimulatorFactory
from sim.faassim import Simulation

logger = logging.getLogger(__name__)


def main():
    """
    运行基础仿真并提取指标表。

    流程：
    1. 创建基础拓扑和基础 benchmark。
    2. 使用 ``CustomSimulatorFactory`` 替换默认函数模拟器。
    3. 运行仿真。
    4. 从 ``sim.env.metrics`` 中提取部署、调度、调用、网络和资源相关表。
    5. 对 ``invocations`` 表中的 ``t_exec`` 做一个最小统计示例。
    """
    logging.basicConfig(level=logging.INFO)

    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())

    # 复用 custom_function_sim 示例里的函数执行模型，让 invocations 表产生 t_exec。
    sim.create_simulator_factory = CustomSimulatorFactory

    sim.run()

    # Metrics.extract_dataframe(name) 会把仿真过程中记录的结构化事件转成 DataFrame。
    dfs = {
        'allocation_df': sim.env.metrics.extract_dataframe('allocation'),
        'invocations_df': sim.env.metrics.extract_dataframe('invocations'),
        'scale_df': sim.env.metrics.extract_dataframe('scale'),
        'schedule_df': sim.env.metrics.extract_dataframe('schedule'),
        'replica_deployment_df': sim.env.metrics.extract_dataframe('replica_deployment'),
        'function_deployments_df': sim.env.metrics.extract_dataframe('function_deployments'),
        'function_deployment_df': sim.env.metrics.extract_dataframe('function_deployment'),
        'function_deployment_lifecycle_df': sim.env.metrics.extract_dataframe('function_deployment_lifecycle'),
        'functions_df': sim.env.metrics.extract_dataframe('functions'),
        'flow_df': sim.env.metrics.extract_dataframe('flow'),
        'network_df': sim.env.metrics.extract_dataframe('network'),
        'node_utilization_df': sim.env.metrics.extract_dataframe('node_utilization'),
        'function_utilization_df': sim.env.metrics.extract_dataframe('function_utilization'),
        'fets_df': sim.env.metrics.extract_dataframe('fets')
    }

    logger.info('Mean exec time %.6f', dfs['invocations_df']['t_exec'].mean())


if __name__ == '__main__':
    main()
