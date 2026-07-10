"""
Raith21 函数生命周期与执行模拟器。

本模块使用 SimPy Resource 表达 HTTP worker 并发限制，并结合函数画像、数据传输、资源占用和性能退化模型模拟 AI 与普通函数调用。
"""

import logging
from typing import Callable, Optional, Dict

from simpy import Resource

from sim.core import Environment
from sim.docker import pull as docker_pull
from sim.faas import FunctionSimulator, FunctionRequest, FunctionReplica, SimulatorFactory, simulate_data_download, \
    simulate_data_upload, FunctionCharacterization, FunctionContainer


def linear_queue_fet_increase(current_requests: int, max_requests: int) -> float:
    """
    根据当前占用的 worker 数计算线性执行时间放大系数。

    参数:
        current_requests: 当前并发执行请求数。 类型：int。
        max_requests: 允许的最大并发请求数。 类型：int。

    返回:
        float。
    """
    return current_requests / max_requests


class PythonHTTPSimulator(FunctionSimulator):

    """
    基础 Python HTTP 函数模拟器。

    使用 SimPy Resource 限制 worker 并发数，从函数画像采样 FET，并按排队压力缩放执行时间。

    关键字段:
        worker_threads: HTTP 模拟器允许的最大并发 worker 数。
        queue: 用于限制并发并记录等待请求的 SimPy Resource。
        scale: 排队压力到 FET 放大系数的映射函数。
        delay: 预留的固定延迟字段。
        fn: 当前函数容器规格。
        characterization: 当前镜像的执行时间与资源画像。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        初始化 PythonHTTPSimulator。

        建立字段：worker_threads、queue、scale、delay、fn、characterization。

        参数:
            queue: 限制并发 worker 数的 SimPy Resource。 类型：Resource。
            scale: 根据队列占用计算执行时间放大系数的函数。 类型：Callable[[int, int], float]。
            fn: 函数容器规格。 类型：FunctionContainer。
            characterization: 函数执行时间和资源画像组合。 类型：FunctionCharacterization。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.worker_threads = queue.capacity
        self.queue = queue
        self.scale = scale
        self.delay = 0
        self.fn = fn
        self.characterization = characterization

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟基础 HTTP 函数调用。

        请求先竞争一个 worker token；获得 token 后从函数画像采样基础 FET，并根据当前
        worker 占用比例放大执行时间。该基础实现不登记资源画像或性能退化。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。
            request: 函数调用请求。 类型：FunctionRequest。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        # SimPy Resource 同时表达并发上限和等待队列；没有空闲 worker 时请求会阻塞在这里。
        token = self.queue.request()
        yield token  

        # queue.count 包含当前已持有 token 的请求数，因子最小为 1，避免低负载时缩短画像 FET。
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.fn.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor
            yield env.timeout(fet)


        except KeyError:
            pass

        self.queue.release(token)


class PythonHttpSimulatorFactory(SimulatorFactory):

    """
    基础 HTTP 模拟器工厂。

    按 FunctionContainer 的 workers 标签创建队列，并为镜像绑定对应函数画像。

    关键字段:
        fn_characterizations: 镜像名到 FunctionCharacterization 的索引。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        初始化 PythonHttpSimulatorFactory。

        建立字段：fn_characterizations。

        参数:
            fn_characterizations: 镜像名到 FunctionCharacterization 的映射。 类型：Dict[str, FunctionCharacterization]。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        根据函数容器创建对应 FunctionSimulator。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            fn: 函数容器规格。 类型：FunctionContainer。

        返回:
            FunctionSimulator。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return PythonHTTPSimulator(queue, linear_queue_fet_increase, fn, self.fn_characterizations[fn.image])


class FunctionCall:
    """
    节点上的函数调用时间区间。

    记录请求、副本、开始和结束时间，供并发查询与性能退化模型构造输入。

    关键字段:
        replica: 执行请求的副本。
        request: 函数调用请求。
        start: 调用开始仿真时间。
        end: 调用结束仿真时间；未完成时为 None。
    """
    replica: FunctionReplica
    request: FunctionRequest
    start: int
    end: Optional[int] = None

    def __init__(self, request, replica, start, end=None):
        """
        初始化 FunctionCall。

        建立字段：request、replica、start、end。

        参数:
            request: 函数调用请求。
            replica: 正在部署或执行的函数副本。
            start: 调用开始仿真时间。
            end: 调用结束仿真时间；None 表示尚未结束。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.request = request
        self.replica = replica
        self.start = start
        self.end = end

    @property
    def request_id(self):
        """
        返回底层 FunctionRequest 的唯一编号。

        返回:
            计算、查询或构造得到的结果。
        """
        return self.request.request_id


class InterferenceAwarePythonHttpSimulatorFactory(SimulatorFactory):

    """
    干扰感知 HTTP 模拟器工厂。

    为函数副本创建能够读取节点历史调用和性能退化模型的模拟器。

    关键字段:
        fn_characterizations: 镜像名到 FunctionCharacterization 的索引。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        初始化 InterferenceAwarePythonHttpSimulatorFactory。

        建立字段：fn_characterizations。

        参数:
            fn_characterizations: 镜像名到 FunctionCharacterization 的映射。 类型：Dict[str, FunctionCharacterization]。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        根据函数容器创建对应 FunctionSimulator。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            fn: 函数容器规格。 类型：FunctionContainer。

        返回:
            FunctionSimulator。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return InterferenceAwarePythonHttpSimulator(queue, linear_queue_fet_increase, fn,
                                                    self.fn_characterizations[fn.image])


class AIPythonHTTPSimulatorFactory(SimulatorFactory):

    """
    AI 函数模拟器工厂。

    为 AI 镜像创建包含模型数据下载、执行和可选结果上传阶段的模拟器。

    关键字段:
        fn_characterizations: 镜像名到 FunctionCharacterization 的索引。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        初始化 AIPythonHTTPSimulatorFactory。

        建立字段：fn_characterizations。

        参数:
            fn_characterizations: 镜像名到 FunctionCharacterization 的映射。 类型：Dict[str, FunctionCharacterization]。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        根据函数容器创建对应 FunctionSimulator。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            fn: 函数容器规格。 类型：FunctionContainer。

        返回:
            FunctionSimulator。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return AIPythonHTTPSimulator(queue, linear_queue_fet_increase, fn, self.fn_characterizations[fn.image])


class AIPythonHTTPSimulator(FunctionSimulator):
    """
    AI Python HTTP 函数模拟器。

    模拟镜像拉取、模型 setup、worker 排队、FET、数据下载/上传和调用指标。

    关键字段:
        worker_threads: HTTP 模拟器允许的最大并发 worker 数。
        queue: 用于限制并发并记录等待请求的 SimPy Resource。
        scale: 排队压力到 FET 放大系数的映射函数。
        deployment: 当前函数容器/部署配置。
        delay: 预留的固定延迟字段。
        characterization: 当前镜像的执行时间与资源画像。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        初始化 AIPythonHTTPSimulator。

        建立字段：worker_threads、queue、scale、deployment、delay、characterization。

        参数:
            queue: 限制并发 worker 数的 SimPy Resource。 类型：Resource。
            scale: 根据队列占用计算执行时间放大系数的函数。 类型：Callable[[int, int], float]。
            fn: 函数容器规格。 类型：FunctionContainer。
            characterization: 函数执行时间和资源画像组合。 类型：FunctionCharacterization。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.worker_threads = queue.capacity
        self.queue = queue
        self.scale = scale
        self.deployment = fn
        self.delay = 0
        self.characterization = characterization

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        yield from docker_pull(env, replica.image, replica.node.ether_node)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        为 AI 推理函数下载模型数据。

        只有镜像名包含 inference 时在 setup 阶段下载；训练和预处理函数的数据在每次
        invoke 时读取，因为它们处理的是请求级输入而不是副本级模型。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        image = replica.pod.spec.containers[0].image
        if 'inference' in image:
            yield from simulate_data_download(env, replica)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟一次 AI 函数请求。

        请求经历 worker 排队、FET 采样、可选输入下载、函数执行和可选输出上传。
        inference 模型已在 setup 下载；preprocessing/training 的数据按请求传输。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。
            request: 函数调用请求。 类型：FunctionRequest。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        # 记录 token 等待区间，最终写入 FET 指标用于区分排队和执行耗时。
        token = self.queue.request()
        t_wait_start = env.now
        yield token  
        t_wait_end = env.now
        t_fet_start = env.now
        
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.deployment.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor

            image = replica.pod.spec.containers[0].image
            if 'preprocessing' in image or 'training' in image:
                # 预处理/训练输入属于请求数据，因此在每次调用开始前下载。
                yield from simulate_data_download(env, replica)
            start = env.now
            call = FunctionCall(request, replica, start)
            # 历史调用区间供 NodeState 查询并发关系，也可被干扰感知模拟器复用。
            replica.node.all_requests.append(call)
            yield env.timeout(fet)
            if 'preprocessing' in image or 'training' in image:
                # 这两类函数会产生需要写回对象存储的结果。
                yield from simulate_data_upload(env, replica)
            t_fet_end = env.now
            env.metrics.log_fet(request.name, replica.image, replica.node.name, t_fet_start, t_fet_end,
                                id(replica), request.request_id, t_wait_start=t_wait_start, t_wait_end=t_wait_end)
            replica.node.set_end(request.request_id, t_fet_end)
        except KeyError:
            pass

        self.queue.release(token)


class InterferenceAwarePythonHttpSimulator(FunctionSimulator):
    """
    资源争用感知函数模拟器。

    除基础 HTTP 生命周期外，还登记函数资源占用、维护节点调用历史，并用退化模型修正执行时间。

    关键字段:
        worker_threads: HTTP 模拟器允许的最大并发 worker 数。
        queue: 用于限制并发并记录等待请求的 SimPy Resource。
        scale: 排队压力到 FET 放大系数的映射函数。
        deployment: 当前函数容器/部署配置。
        delay: 预留的固定延迟字段。
        characterization: 当前镜像的执行时间与资源画像。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        初始化 InterferenceAwarePythonHttpSimulator。

        建立字段：worker_threads、queue、scale、deployment、delay、characterization。

        参数:
            queue: 限制并发 worker 数的 SimPy Resource。 类型：Resource。
            scale: 根据队列占用计算执行时间放大系数的函数。 类型：Callable[[int, int], float]。
            fn: 函数容器规格。 类型：FunctionContainer。
            characterization: 函数执行时间和资源画像组合。 类型：FunctionCharacterization。

        返回:
            无显式返回值；主要通过更新对象状态、写入指标或产生文件输出生效。
        """
        self.worker_threads = queue.capacity
        self.queue = queue
        self.scale = scale
        self.deployment = fn
        self.delay = 0
        self.characterization = characterization

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        模拟函数副本部署阶段。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        yield from docker_pull(env, replica.image, replica.node.ether_node)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        为干扰感知 AI 推理函数下载模型数据。

        与 AIPythonHTTPSimulator 相同，副本级模型只下载一次；请求级输入在 invoke 中处理。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        image = replica.pod.spec.containers[0].image
        if 'inference' in image:
            yield from simulate_data_download(env, replica)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        模拟考虑资源争用的函数调用。

        在基础 FET 之后，根据该时间窗口内的并发调用构造退化模型输入，再追加退化延迟。
        调用区间会写入 NodeState.all_requests，并在结束时补齐 end 时间。

        参数:
            env: faas-sim 仿真环境。 类型：Environment。
            replica: 正在部署或执行的函数副本。 类型：FunctionReplica。
            request: 函数调用请求。 类型：FunctionRequest。

        产出:
            SimPy 事件序列；调用方需要通过 yield from 或 env.process() 驱动该流程。
        """
        token = self.queue.request()
        t_wait_start = env.now
        yield token  
        t_wait_end = env.now
        t_fet_start = env.now
        
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.deployment.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor

            image = replica.pod.spec.containers[0].image
            if 'preprocessing' in image or 'training' in image:
                yield from simulate_data_download(env, replica)
            start = env.now
            call = FunctionCall(request, replica, start)
            replica.node.all_requests.append(call)
            yield env.timeout(fet)

            # 基础 FET 结束后估计该窗口的总退化比例；只追加超过基础 FET 的部分。
            end = env.now
            degradation = replica.node.estimate_degradation(self.characterization.resource_oracle, start, end)
            delay = max(0, (fet * degradation) - fet)
            yield env.timeout(delay)
            if 'preprocessing' in image or 'training' in image:
                yield from simulate_data_upload(env, replica)
            t_fet_end = env.now
            env.metrics.log_fet(request.name, replica.image, replica.node.name, t_fet_start, t_fet_end,
                                t_wait_start, t_wait_end, degradation,
                                id(replica))
            replica.node.set_end(request.request_id, t_fet_end)
        except KeyError:
            pass

        self.queue.release(token)
