"""
文件作用：data_locality 样例使用的函数生命周期模拟器。

该模拟器在 setup 阶段调用 faas-sim 原生 simulate_data_download()，
从而根据 FunctionContainer 标签声明的数据路径，从 StorageIndex 指定的存储节点下载数据。
"""

import logging

import sim.docker as docker
from sim.core import Environment
from sim.faas import (
    FunctionSimulator,
    FunctionReplica,
    FunctionRequest,
    SimulatorFactory,
    FunctionContainer,
    simulate_data_download,
)

logger = logging.getLogger(__name__)


class DataLocalitySimulatorFactory(SimulatorFactory):
    """
    data_locality 样例的函数模拟器工厂。
    """

    def __init__(self, scenario_name: str):
        """
        初始化工厂。

        参数：
        - scenario_name：实验场景名，例如 data_locality_aware 或 forced_remote。
        """
        self.scenario_name = scenario_name

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        创建函数生命周期模拟器。
        """
        return DataLocalityFunctionSimulator(self.scenario_name)


class DataLocalityFunctionSimulator(FunctionSimulator):
    """
    数据本地性函数生命周期模拟器。

    样例重点：
    - deploy 阶段拉取镜像；
    - setup 阶段下载输入数据；
    - setup 数据下载耗时受调度节点与数据存储节点之间的网络路径影响；
    - invoke 阶段只保留固定业务执行时间。
    """

    def __init__(self, scenario_name: str):
        """
        初始化模拟器。
        """
        self.scenario_name = scenario_name

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段，包含镜像拉取。
        """
        yield from docker.pull(env, replica.container.image, replica.node.ether_node)

    def startup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本启动阶段。
        """
        logger.info(
            "[simtime=%.2f] startup replica for function %s on node %s",
            env.now,
            replica.function.name,
            replica.node.name,
        )
        yield env.timeout(0.15)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本业务初始化阶段，并执行数据下载。

        simulate_data_download() 会读取 replica.pod.spec.labels 中的：
        - data.skippy.io/receives-from-storage
        - data.skippy.io/receives-from-storage/path

        然后根据 env.storage_index / env.cluster.storage_index 找到数据所在存储节点。
        """
        labels = replica.pod.spec.labels
        data_path = labels.get("data.skippy.io/receives-from-storage/path")
        data_size = labels.get("data.skippy.io/receives-from-storage")

        storage_nodes = []
        if data_path:
            storage_nodes = env.cluster.get_storage_nodes(data_path)

        started = env.now

        logger.info(
            "[simtime=%.2f] setup data download function=%s node=%s data_path=%s storage_nodes=%s",
            env.now,
            replica.function.name,
            replica.node.name,
            data_path,
            storage_nodes,
        )

        yield from simulate_data_download(env, replica)

        duration = env.now - started

        logger.info(
            "[simtime=%.2f] finish data download function=%s node=%s duration=%.6f",
            env.now,
            replica.function.name,
            replica.node.name,
            duration,
        )

        env.metrics.log(
            "data_locality_download",
            {
                "download_duration": duration,
                "storage_node_count": len(storage_nodes),
            },
            scenario=self.scenario_name,
            function_name=replica.function.name,
            node_name=replica.node.name,
            data_path=data_path,
            data_size=data_size,
            storage_nodes=";".join(storage_nodes),
            replica_id=id(replica),
        )

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次函数调用。

        本样例重点是数据下载阶段，业务执行阶段使用固定短耗时。
        """
        cpu_millis = replica.node.capacity.cpu_millis * 0.1

        env.resource_state.put_resource(replica, "cpu", cpu_millis)
        replica.node.current_requests.add(request)

        yield env.timeout(0.1)

        replica.node.current_requests.remove(request)
        env.resource_state.remove_resource(replica, "cpu", cpu_millis)

    def teardown(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本关闭阶段。
        """
        yield env.timeout(0)
