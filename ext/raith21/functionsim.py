"""
文件作用：Raith21 函数执行模拟器，基于函数画像和资源 Oracle 模拟 HTTP 函数队列、AI 推理 setup、资源占用和干扰退化。
主要类：PythonHTTPSimulator、PythonHttpSimulatorFactory、FunctionCall、InterferenceAwarePythonHttpSimulatorFactory、AIPythonHTTPSimulatorFactory、AIPythonHTTPSimulator、InterferenceAwarePythonHttpSimulator。
主要函数：linear_queue_fet_increase。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
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
    函数作用：处理 linear、queue、fet、increase 相关业务逻辑。
    关键流程：
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：current_requests：节点当前正在执行的函数调用记录，用于并发和干扰计算。；max_requests：最大并发请求数，用于计算队列拥塞或性能退化。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    return current_requests / max_requests


class PythonHTTPSimulator(FunctionSimulator):

    """
    类作用：Python HTTP 函数模拟器，使用队列限制并发并按画像采样执行时间。
    继承关系：FunctionSimulator。
    核心方法：__init__、invoke。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：characterization、delay、fn、queue、scale、worker_threads。
        参数：queue：并发队列或 worker 限制。；scale：执行时间缩放因子。；fn：函数定义对象或函数名。；characterization：函数画像对象。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.worker_threads：HTTP watchdog 的 worker 并发数，限制同一副本可同时处理的请求数量。
        self.worker_threads = queue.capacity
        # 字段说明：self.queue：SimPy 资源队列，用于限制 HTTP 模式下的并发 worker 数。
        self.queue = queue
        # 字段说明：self.scale：函数执行时间缩放因子，用于实验中放大或缩短耗时。
        self.scale = scale
        # 字段说明：self.delay：模拟阶段延迟，用于通过 env.timeout 推进仿真时间。
        self.delay = 0
        # 字段说明：self.fn：函数定义对象，保存函数名称、镜像集合和标签。
        self.fn = fn
        # 字段说明：self.characterization：函数画像对象，提供执行时间和资源使用估计。
        self.characterization = characterization

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        token = self.queue.request()
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield token  

        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.fn.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(fet)


        except KeyError:
            pass

        self.queue.release(token)


class PythonHttpSimulatorFactory(SimulatorFactory):

    """
    类作用：Python HTTP 模拟器工厂，按函数名选择画像并创建 PythonHTTPSimulator。
    继承关系：SimulatorFactory。
    核心方法：__init__、create。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn_characterizations。
        参数：fn_characterizations：按函数名索引的函数画像集合。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn_characterizations：按函数名索引的函数画像集合。
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return PythonHTTPSimulator(queue, linear_queue_fet_increase, fn, self.fn_characterizations[fn.image])


class FunctionCall:
    """
    类作用：函数调用区间记录，保存请求、副本、开始时间和结束时间，用于并发干扰计算。
    核心字段：replica：函数副本对象。；request：函数请求对象，保存请求目标、编号和数据大小。；start：函数调用或生命周期阶段开始时间。；end：函数调用结束时间。。
    核心方法：__init__、request_id。
    """
    # 字段说明：replica：函数副本对象。
    replica: FunctionReplica
    # 字段说明：request：函数请求对象，保存请求目标、编号和数据大小。
    request: FunctionRequest
    # 字段说明：start：函数调用或生命周期阶段开始时间。
    start: int
    # 字段说明：end：函数调用结束时间。
    end: Optional[int] = None

    def __init__(self, request, replica, start, end=None):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：end、replica、request、start。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。；replica：正在部署、执行或释放的函数副本。；start：函数调用或生命周期阶段开始时间。；end：函数调用结束时间。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.request：函数请求对象，保存请求目标、编号和数据大小。
        self.request = request
        # 字段说明：self.replica：函数副本对象。
        self.replica = replica
        # 字段说明：self.start：函数调用或生命周期阶段开始时间。
        self.start = start
        # 字段说明：self.end：函数调用结束时间。
        self.end = end

    @property
    def request_id(self):
        """
        函数作用：处理 request、id 相关业务逻辑。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.request.request_id


class InterferenceAwarePythonHttpSimulatorFactory(SimulatorFactory):

    """
    类作用：干扰感知模拟器工厂，为函数副本创建能读取并发调用状态的 HTTP 模拟器。
    继承关系：SimulatorFactory。
    核心方法：__init__、create。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn_characterizations。
        参数：fn_characterizations：按函数名索引的函数画像集合。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn_characterizations：按函数名索引的函数画像集合。
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return InterferenceAwarePythonHttpSimulator(queue, linear_queue_fet_increase, fn,
                                                    self.fn_characterizations[fn.image])


class AIPythonHTTPSimulatorFactory(SimulatorFactory):

    """
    类作用：AI HTTP 模拟器工厂，为 AI 推理/训练函数创建包含模型加载阶段的模拟器。
    继承关系：SimulatorFactory。
    核心方法：__init__、create。
    """
    def __init__(self, fn_characterizations: Dict[str, FunctionCharacterization]):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：fn_characterizations。
        参数：fn_characterizations：按函数名索引的函数画像集合。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.fn_characterizations：按函数名索引的函数画像集合。
        self.fn_characterizations = fn_characterizations

    def create(self, env: Environment, fn: FunctionContainer) -> FunctionSimulator:
        """
        函数作用：根据输入对象创建对应的业务组件实例。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        workers = int(fn.labels['workers'])
        queue = Resource(env=env, capacity=workers)
        return AIPythonHTTPSimulator(queue, linear_queue_fet_increase, fn, self.fn_characterizations[fn.image])


class AIPythonHTTPSimulator(FunctionSimulator):
    """
    类作用：AI Python HTTP 模拟器，显式模拟部署、模型 setup、请求执行和资源占用。
    继承关系：FunctionSimulator。
    核心方法：__init__、deploy、setup、invoke。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：characterization、delay、deployment、queue、scale、worker_threads。
        参数：queue：并发队列或 worker 限制。；scale：执行时间缩放因子。；fn：函数定义对象或函数名。；characterization：函数画像对象。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.worker_threads：HTTP watchdog 的 worker 并发数，限制同一副本可同时处理的请求数量。
        self.worker_threads = queue.capacity
        # 字段说明：self.queue：SimPy 资源队列，用于限制 HTTP 模式下的并发 worker 数。
        self.queue = queue
        # 字段说明：self.scale：函数执行时间缩放因子，用于实验中放大或缩短耗时。
        self.scale = scale
        # 字段说明：self.deployment：函数部署对象，包含函数定义、容器规格和伸缩配置。
        self.deployment = fn
        # 字段说明：self.delay：模拟阶段延迟，用于通过 env.timeout 推进仿真时间。
        self.delay = 0
        # 字段说明：self.characterization：函数画像对象，提供执行时间和资源使用估计。
        self.characterization = characterization

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
        关键流程：
        - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from docker_pull(env, replica.image, replica.node.ether_node)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        关键流程：
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        image = replica.pod.spec.containers[0].image
        if 'inference' in image:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield from simulate_data_download(env, replica)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        token = self.queue.request()
        t_wait_start = env.now
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield token  
        t_wait_end = env.now
        t_fet_start = env.now
        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.deployment.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor

            image = replica.pod.spec.containers[0].image
            if 'preprocessing' in image or 'training' in image:
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from simulate_data_download(env, replica)
            start = env.now
            call = FunctionCall(request, replica, start)
            replica.node.all_requests.append(call)
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(fet)
            if 'preprocessing' in image or 'training' in image:
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from simulate_data_upload(env, replica)
            t_fet_end = env.now
            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            env.metrics.log_fet(request.name, replica.image, replica.node.name, t_fet_start, t_fet_end,
                                id(replica), request.request_id, t_wait_start=t_wait_start, t_wait_end=t_wait_end)
            replica.node.set_end(request.request_id, t_fet_end)
        except KeyError:
            pass

        self.queue.release(token)


class InterferenceAwarePythonHttpSimulator(FunctionSimulator):
    """
    类作用：干扰感知 Python HTTP 模拟器，根据节点并发调用和退化模型调整执行时间。
    继承关系：FunctionSimulator。
    核心方法：__init__、deploy、setup、invoke。
    """
    def __init__(self, queue: Resource, scale: Callable[[int, int], float], fn: FunctionContainer,
                 characterization: FunctionCharacterization):
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：characterization、delay、deployment、queue、scale、worker_threads。
        参数：queue：并发队列或 worker 限制。；scale：执行时间缩放因子。；fn：函数定义对象或函数名。；characterization：函数画像对象。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.worker_threads：HTTP watchdog 的 worker 并发数，限制同一副本可同时处理的请求数量。
        self.worker_threads = queue.capacity
        # 字段说明：self.queue：SimPy 资源队列，用于限制 HTTP 模式下的并发 worker 数。
        self.queue = queue
        # 字段说明：self.scale：函数执行时间缩放因子，用于实验中放大或缩短耗时。
        self.scale = scale
        # 字段说明：self.deployment：函数部署对象，包含函数定义、容器规格和伸缩配置。
        self.deployment = fn
        # 字段说明：self.delay：模拟阶段延迟，用于通过 env.timeout 推进仿真时间。
        self.delay = 0
        # 字段说明：self.characterization：函数画像对象，提供执行时间和资源使用估计。
        self.characterization = characterization

    def deploy(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
        关键流程：
        - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from docker_pull(env, replica.image, replica.node.ether_node)

    def setup(self, env: Environment, replica: FunctionReplica):
        """
        函数作用：模拟函数业务初始化阶段，例如加载模型、预热缓存或建立连接。
        关键流程：
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        image = replica.pod.spec.containers[0].image
        if 'inference' in image:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield from simulate_data_download(env, replica)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        token = self.queue.request()
        t_wait_start = env.now
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield token  
        t_wait_end = env.now
        t_fet_start = env.now
        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        
        factor = max(1, self.scale(self.queue.count, self.queue.capacity))
        try:
            fet = self.characterization.sample_fet(replica.node.name)
            if fet is None:
                logging.error(f"FET for node {replica.node.name} for function {self.deployment.image} was not found")
                raise ValueError(f'{replica.node.name}')
            fet = float(fet) * factor

            image = replica.pod.spec.containers[0].image
            if 'preprocessing' in image or 'training' in image:
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from simulate_data_download(env, replica)
            start = env.now
            call = FunctionCall(request, replica, start)
            replica.node.all_requests.append(call)
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(fet)

            
            end = env.now
            degradation = replica.node.estimate_degradation(self.characterization.resource_oracle, start, end)
            delay = max(0, (fet * degradation) - fet)
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(delay)
            if 'preprocessing' in image or 'training' in image:
                # 仿真推进：向 SimPy 事件队列交出控制权。
                yield from simulate_data_upload(env, replica)
            t_fet_end = env.now
            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            env.metrics.log_fet(request.name, replica.image, replica.node.name, t_fet_start, t_fet_end,
                                t_wait_start, t_wait_end, degradation,
                                id(replica))
            replica.node.set_end(request.request_id, t_fet_end)
        except KeyError:
            pass

        self.queue.release(token)
