"""
文件作用：结果分析示例，读取仿真输出指标并计算/展示关键实验结果。
主要函数：main。
在整体架构中的位置：属于示例层，演示用户如何组合核心组件完成实验。
"""

import logging

import examples.basic.main as basic
from examples.custom_function_sim.main import CustomSimulatorFactory
from sim.faassim import Simulation

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


def main():
    """
    函数作用：处理 main 相关业务逻辑。
    关键流程：
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    logging.basicConfig(level=logging.INFO)

    # 业务说明：这里将仿真事件写入指标/日志，供实验分析使用。
    sim = Simulation(basic.example_topology(), basic.ExampleBenchmark())

    
    sim.create_simulator_factory = CustomSimulatorFactory

    
    sim.run()

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

    logger.info('Mean exec time %d', dfs['invocations_df']['t_exec'].mean())


if __name__ == '__main__':
    main()
