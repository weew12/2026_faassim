"""
文件作用：默认 FaaS 平台实现文件，负责函数部署、副本创建、调度队列、调用转发、扩缩容、挂起与删除等完整业务流程。
主要类：DefaultFaasSystem。
主要函数：simulate_function_start、simulate_data_download、simulate_data_upload、simulate_function_invocation。
在整体架构中的位置：属于 faas-sim 核心仿真层，直接参与离散事件推进、平台建模或指标采集。
"""

import logging
import time
from collections import defaultdict, Counter
from typing import Dict, List

import simpy
from ether.util import parse_size_string

from sim.core import Environment
from sim.faas import RoundRobinLoadBalancer, FunctionDeployment, FunctionReplica, FunctionContainer, FunctionRequest, \
    FunctionState
from sim.net import SafeFlow
from sim.skippy import create_function_pod
from .core import FaasSystem, FunctionSimulator
from .scaling import FaasRequestScaler, AverageFaasRequestScaler, AverageQueueFaasRequestScaler

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)


class DefaultFaasSystem(FaasSystem):
    """
    类作用：默认 FaaS 系统实现，串联调度器、负载均衡器、生命周期协程、扩缩容和指标记录。
    继承关系：FaasSystem。
    核心方法：__init__、get_deployments、get_function_index、get_replicas、deploy、deploy_replica、invoke、remove、scale_down、choose_replicas_to_remove、scale_up、next_replica 等。
    """

    # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
    
    def __init__(self, env: Environment, scale_by_requests: bool = False,
                 scale_by_average_requests: bool = False, scale_by_queue_requests_per_replica: bool = False) -> None:
        """
        函数作用：初始化对象字段，并把外部配置转换为后续业务流程可直接读取的内部状态。
        关键流程：
        - 写入对象字段：avg_faas_scalers、env、faas_scalers、function_containers、functions_definitions、functions_deployments、load_balancer、queue_faas_scalers、replica_count、replicas、request_queue、scale_by_average_requests_per_replica、scale_by_queue_requests_per_replica、scale_by_requests、scheduler_queue。
        参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；scale_by_requests：是否启用基于请求总数的自动伸缩策略。；scale_by_average_requests：是否启用基于平均请求速率的自动伸缩策略。；scale_by_queue_requests_per_replica：是否启用基于每副本队列长度的自动伸缩策略。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        # 字段说明：self.env：仿真全局环境引用，用于访问 SimPy 时钟、拓扑、指标、资源状态和 FaaS 系统。
        self.env = env
        # 字段说明：self.function_containers：函数容器索引，按函数名保存可部署容器规格。
        self.function_containers = dict()
        
        # 字段说明：self.replicas：函数副本列表或副本数量，表示平台当前/目标运行实例规模。
        self.replicas = defaultdict(list)

        # 字段说明：self.request_queue：请求队列，用于模拟请求进入平台后的排队过程。
        self.request_queue = simpy.Store(env)
        # 字段说明：self.scheduler_queue：待调度副本队列，保证副本调度按事件顺序执行。
        self.scheduler_queue = simpy.Store(env)

        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        # 字段说明：self.load_balancer：负载均衡器，负责为函数请求选择运行副本。
        self.load_balancer = RoundRobinLoadBalancer(env, self.replicas)

        # 字段说明：self.functions_deployments：函数部署索引，按函数名保存平台已部署的 FunctionDeployment。
        self.functions_deployments: Dict[str, FunctionDeployment] = dict()
        # 字段说明：self.replica_count：计数字段，用于记录对象数量或循环次数。
        self.replica_count: Dict[str, int] = dict()
        # 字段说明：self.functions_definitions：函数定义计数器，统计函数部署/删除过程中的定义引用情况。
        self.functions_definitions = Counter()

        # 字段说明：self.scale_by_requests：是否启用基于请求总数的自动伸缩策略。
        self.scale_by_requests = scale_by_requests
        # 字段说明：self.scale_by_average_requests_per_replica：是否启用基于每副本平均 RPS 的自动伸缩策略。
        self.scale_by_average_requests_per_replica = scale_by_average_requests
        # 字段说明：self.scale_by_queue_requests_per_replica：是否启用基于每副本队列长度的自动伸缩策略。
        self.scale_by_queue_requests_per_replica = scale_by_queue_requests_per_replica
        # 字段说明：self.faas_scalers：基于请求数的伸缩器索引，按函数名保存后台伸缩进程。
        self.faas_scalers: Dict[str, FaasRequestScaler] = dict()
        # 字段说明：self.avg_faas_scalers：基于平均 RPS 的伸缩器索引，按函数名保存后台伸缩进程。
        self.avg_faas_scalers: Dict[str, AverageFaasRequestScaler] = dict()
        # 字段说明：self.queue_faas_scalers：基于队列长度的伸缩器索引，按函数名保存后台伸缩进程。
        self.queue_faas_scalers: Dict[str, AverageQueueFaasRequestScaler] = dict()

    def get_deployments(self) -> List[FunctionDeployment]:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return list(self.functions_deployments.values())

    def get_function_index(self) -> Dict[str, FunctionContainer]:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.function_containers

    def get_replicas(self, fn_name: str, state=None) -> List[FunctionReplica]:
        """
        函数作用：读取或构造指定业务对象，作为部署、调度、统计或实验装配的输入。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_name：目标函数名称。；state：副本生命周期状态过滤条件。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        if state is None:
            return self.replicas[fn_name]

        return [replica for replica in self.replicas[fn_name] if replica.state == state]

    def deploy(self, fd: FunctionDeployment):
        """
        函数作用：部署函数或函数副本，使其进入平台管理范围并准备后续调用。
        关键流程：
        - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：fd：函数部署对象，包含函数、容器规格和伸缩配置。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        if fd.name in self.functions_deployments:
            raise ValueError('function already deployed')

        self.functions_deployments[fd.name] = fd
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        self.faas_scalers[fd.name] = FaasRequestScaler(fd, self.env)
        self.avg_faas_scalers[fd.name] = AverageFaasRequestScaler(fd, self.env)
        self.queue_faas_scalers[fd.name] = AverageQueueFaasRequestScaler(fd, self.env)

        if self.scale_by_requests:
            self.env.process(self.faas_scalers[fd.name].run())
        if self.scale_by_average_requests_per_replica:
            self.env.process(self.avg_faas_scalers[fd.name].run())
        if self.scale_by_queue_requests_per_replica:
            self.env.process(self.queue_faas_scalers[fd.name].run())

        for f in fd.fn_containers:
            self.function_containers[f.image] = f

        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_function_deployment(fd)
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_function_deployment_lifecycle(fd, 'deploy')
        logger.info('deploying function %s with scale_min=%d', fd.name, fd.scaling_config.scale_min)
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from self.scale_up(fd.name, fd.scaling_config.scale_min)

    def deploy_replica(self, fd: FunctionDeployment, fn: FunctionContainer, services: List[FunctionContainer]):
        """
        函数作用：创建并调度单个函数副本，然后启动其生命周期协程。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 调用调度器或调度评分逻辑，为副本选择候选节点。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：fd：函数部署对象，包含函数、容器规格和伸缩配置。；fn：函数定义对象或函数名。；services：函数部署包含的容器规格列表。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        replica = self.create_replica(fd, fn)
        self.replicas[fd.name].append(replica)
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_queue_schedule(replica)
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_function_replica(replica)
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield self.scheduler_queue.put((replica, services))

    def invoke(self, request: FunctionRequest):
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        """
        函数作用：处理一次函数调用请求，包括选择副本、等待可用实例、执行模拟器并记录指标。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        logger.debug('invoking function %s', request.name)

        if request.name not in self.functions_deployments.keys():
            logger.warning('invoking non-existing function %s', request.name)
            return

        t_received = self.env.now

        replicas = self.get_replicas(request.name, FunctionState.RUNNING)
        if not replicas:
            '''
            https://docs.openfaas.com/architecture/autoscaling/#scaling-up-from-zero-replicas

            When scale_from_zero is enabled a cache is maintained in memory indicating the readiness of each function.
            If when a request is received a function is not ready, then the HTTP connection is blocked, the function is
            scaled to min replicas, and as soon as a replica is available the request is proxied through as per normal.
            You will see this process taking place in the logs of the gateway component.
            '''
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield from self.poll_available_replica(request.name)

        if len(replicas) < 1:
            raise ValueError
        elif len(replicas) > 1:
            logger.debug('asking load balancer for replica for request %s:%d', request.name, request.request_id)
            replica = self.next_replica(request)
        else:
            replica = replicas[0]

        logger.debug('dispatching request %s:%d to %s', request.name, request.request_id, replica.node.name)

        t_start = self.env.now
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from simulate_function_invocation(self.env, replica, request)

        t_end = self.env.now

        t_wait = t_start - t_received
        t_exec = t_end - t_start
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_invocation(request.name, replica.image, replica.node.name, t_wait, t_start,
                                        t_exec, id(replica))

    def remove(self, fn: FunctionDeployment):
        """
        函数作用：删除函数部署并清理其所有运行副本。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：fn：函数定义对象或函数名。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_function_deployment_lifecycle(fn, 'remove')

        replica_count = self.replica_count[fn.name]
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from self.scale_down(fn.name, replica_count)
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        self.faas_scalers[fn.name].stop()
        self.avg_faas_scalers[fn.name].stop()
        self.queue_faas_scalers[fn.name].stop()

        del self.functions_deployments[fn.name]
        del self.faas_scalers[fn.name]
        del self.avg_faas_scalers[fn.name]
        del self.queue_faas_scalers[fn.name]
        del self.replica_count[fn.name]
        for container in fn.fn_containers:
            del self.functions_definitions[container.image]

    def scale_down(self, fn_name: str, remove: int):
        """
        函数作用：缩减函数副本数，选择待删除副本并执行生命周期清理。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_name：目标函数名称。；remove：需要移除的副本数量或副本列表。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        replica_count = len(self.get_replicas(fn_name, FunctionState.RUNNING))
        if replica_count == 0:
            return
        replica_count -= remove
        if replica_count <= 0:
            remove = remove + replica_count

        scale_min = self.functions_deployments[fn_name].scaling_config.scale_min
        if self.replica_count.get(fn_name, 0) - remove < scale_min:
            remove = self.replica_count.get(fn_name, 0) - scale_min

        if replica_count - remove <= 0 or remove == 0:
            return

        logger.info(f'scale down {fn_name} by {remove}')
        replicas = self.choose_replicas_to_remove(fn_name, remove)
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_scaling(fn_name, -remove)
        for replica in replicas:
            # 仿真推进：向 SimPy 事件队列交出控制权。
            yield from self._remove_replica(replica)
            replicas.remove(replica)

    def choose_replicas_to_remove(self, fn_name: str, n: int):
        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        """
        函数作用：按照默认策略选择最适合被缩减的副本。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_name：目标函数名称。；n：数量参数。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        running_replicas = self.get_replicas(fn_name, FunctionState.RUNNING)
        return running_replicas[len(running_replicas) - n:]

    def scale_up(self, fn_name: str, replicas: int):
        """
        函数作用：增加函数副本数，在伸缩上限内创建并调度新副本。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 调用部署接口上线函数或副本。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fn_name：目标函数名称。；replicas：副本数量或副本列表。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        fd = self.functions_deployments[fn_name]
        config = fd.scaling_config
        ranking = fd.ranking

        scale = replicas
        if self.replica_count.get(fn_name, None) is None:
            self.replica_count[fn_name] = 0

        if self.replica_count[fn_name] >= config.scale_max:
            logger.debug('Function %s wanted to scale up, but maximum number of replicas reached', fn_name)
            return

        # 业务说明：这里处理函数请求生成、调用执行或调用指标记录。
        if self.replica_count[fn_name] + replicas > config.scale_max:
            reduce = self.replica_count[fn_name] + replicas - config.scale_max
            scale = replicas - reduce

        if scale == 0:
            return
        actually_scaled = 0
        for index, service in enumerate(fd.get_services()):
            
            leftover_scale = scale
            max_replicas = int(ranking.function_factor[service.image] * config.scale_max)

            
            if max_replicas * config.scale_max < leftover_scale + self.functions_definitions[
                service.image]:

                
                reduce = max_replicas - self.functions_definitions[service.image]
                if reduce < 0:
                    
                    continue
                leftover_scale = leftover_scale - reduce
            if leftover_scale > 0:
                for _ in range(leftover_scale):
                    # 仿真推进：向 SimPy 事件队列交出控制权。
                    yield from self.deploy_replica(fd, fd.get_container(service.image), fd.get_containers()[index:])
                    actually_scaled += 1
                    scale -= 1

        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_scaling(fd.name, actually_scaled)

        if scale > 0:
            logger.debug("Function %s wanted to scale, but not all requested replicas were deployed: %s", fn_name,
                         str(scale))

    def next_replica(self, request) -> FunctionReplica:
        """
        函数作用：根据负载均衡策略为请求选择下一 个可用副本。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return self.load_balancer.next_replica(request)

    def start(self):
        """
        函数作用：启动 FaaS 系统后台进程，例如调度 worker 和伸缩器。
        关键流程：
        - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
        - 调用调度器或调度评分逻辑，为副本选择候选节点。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        for process in self.env.background_processes:
            self.env.process(process(self.env))
        self.env.process(self.run_scheduler_worker())

    def poll_available_replica(self, fn: str, interval=0.5):
        """
        函数作用：周期性等待目标函数出现 RUNNING 副本。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        参数：fn：函数定义对象或函数名。；interval：轮询或采样间隔。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        while not self.get_replicas(fn, FunctionState.RUNNING):
            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield self.env.timeout(interval)

    def run_scheduler_worker(self):
        """
        函数作用：调度队列消费者，按顺序取出待调度副本并调用调度器绑定节点。
        关键流程：
        - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
        - 通过 env.process 串联子协程，使部署、调用或监控流程按 SimPy 事件顺序执行。
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 调用部署接口上线函数或副本。
        - 调用调度器或调度评分逻辑，为副本选择候选节点。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        env = self.env

        while True:
            replica: FunctionReplica
            replica, services = yield self.scheduler_queue.get()

            logger.debug('scheduling next replica %s', replica.function.name)

            # 业务说明：这里与副本放置或调度决策有关。
            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            self.env.metrics.log_start_schedule(replica)
            pod = replica.pod
            then = time.time()
            result = env.scheduler.schedule(pod)
            duration = time.time() - then
            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            self.env.metrics.log_finish_schedule(replica, result)

            # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
            yield env.timeout(duration)  

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('Pod scheduling took %.2f ms, and yielded %s', duration * 1000, result)

            if not result.suggested_host:
                self.replicas[replica.fn_name].remove(replica)
                if len(services) > 0:
                    logger.warning('retry scheduling pod %s', pod.name)
                    # 仿真推进：向 SimPy 事件队列交出控制权。
                    yield from self.deploy_replica(replica.function, services[0], services[1:])
                else:
                    logger.error('pod %s cannot be scheduled', pod.name)

                continue

            logger.info('pod %s was scheduled to %s', pod.name, result.suggested_host)

            replica.node = self.env.get_node_state(result.suggested_host.name)
            node = replica.node.skippy_node

            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            env.metrics.log('allocation', {
                'cpu': 1 - (node.allocatable.cpu_millis / node.capacity.cpu_millis),
                'mem': 1 - (node.allocatable.memory / node.capacity.memory)
            }, node=node.name)

            self.functions_definitions[replica.image] += 1
            self.replica_count[replica.fn_name] += 1

            # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
            self.env.metrics.log_function_deploy(replica)
            
            env.process(simulate_function_start(env, replica))

    def create_pod(self, fd: FunctionDeployment, fn: FunctionContainer):
        """
        函数作用：把 FunctionReplica 转换为调度器可处理的 Pod 表示。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fd：函数部署对象，包含函数、容器规格和伸缩配置。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return create_function_pod(fd, fn)

    def create_replica(self, fd: FunctionDeployment, fn: FunctionContainer) -> FunctionReplica:
        """
        函数作用：根据函数部署和容器规格构造 FunctionReplica 运行时对象。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：fd：函数部署对象，包含函数、容器规格和伸缩配置。；fn：函数定义对象或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        replica = FunctionReplica()
        replica.function = fd
        replica.container = fn
        replica.pod = self.create_pod(fd, fn)
        replica.simulator = self.env.simulator_factory.create(self.env, fn)
        return replica

    def discover(self, function: str) -> List[FunctionReplica]:
        """
        函数作用：查询指定函数当前可见的运行副本列表。
        关键流程：
        - 返回计算结果或被创建的业务对象，供上层流程继续使用。
        参数：function：目标函数定义或函数名。。
        返回：与该业务步骤对应的对象、指标或计算结果。
        """
        return [replica for replica in self.replicas[function] if replica.state == FunctionState.RUNNING]

    def _remove_replica(self, replica: FunctionReplica):
        """
        函数作用：执行单个副本的下线、资源释放和指标记录。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
        参数：replica：正在部署、执行或释放的函数副本。。
        产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
        """
        env = self.env
        node = replica.node.skippy_node

        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        env.metrics.log_teardown(replica)
        # 仿真推进：向 SimPy 事件队列交出控制权。
        yield from replica.simulator.teardown(env, replica)

        self.env.cluster.remove_pod_from_node(replica.pod, node)
        replica.state = FunctionState.SUSPENDED
        self.replicas[replica.function.name].remove(replica)

        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        env.metrics.log('allocation', {
            'cpu': 1 - (node.allocatable.cpu_millis / node.capacity.cpu_millis),
            'mem': 1 - (node.allocatable.memory / node.capacity.memory)
        }, node=node.name)
        self.replica_count[replica.fn_name] -= 1
        self.functions_definitions[replica.image] -= 1

    def suspend(self, function_name: str):
        """
        函数作用：挂起函数部署，使相关副本不再接收请求。
        关键流程：
        - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
        - 根据观测指标触发扩容或缩容，改变函数副本数量。
        - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
        参数：function_name：目标函数名称。。
        返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
        """
        if function_name not in self.functions_deployments.keys():
            raise ValueError

        # 待办：这里保留了后续完善点，需要结合实验目标继续细化。
        replicas: List[FunctionReplica] = self.discover(function_name)
        # 伸缩动作：根据当前观测结果调整函数副本数量。
        self.scale_down(function_name, len(replicas))

        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        self.env.metrics.log_function_deployment_lifecycle(self.functions_deployments[function_name], 'suspend')


def simulate_function_start(env: Environment, replica: FunctionReplica):
    """
    函数作用：按函数模拟器的 startup 和 setup 阶段推进副本启动流程。
    关键流程：
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    - 调用部署接口上线函数或副本。
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    sim: FunctionSimulator = replica.simulator

    logger.debug('deploying function %s to %s', replica.function.name, replica.node.name)
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_deploy(replica)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield from sim.deploy(env, replica)
    replica.state = FunctionState.STARTING
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_startup(replica)
    logger.debug('starting function %s on %s', replica.function.name, replica.node.name)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield from sim.startup(env, replica)

    logger.debug('running function setup %s on %s', replica.function.name, replica.node.name)
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_setup(replica)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield from sim.setup(env, replica)  # 修正提示：这里标记了原实现中需要进一步确认的边界。
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_finish_deploy(replica)
    replica.state = FunctionState.RUNNING


def simulate_data_download(env: Environment, replica: FunctionReplica):
    """
    函数作用：模拟函数从存储节点下载输入数据。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    node = replica.node.ether_node
    func = replica
    started = env.now

    if 'data.skippy.io/receives-from-storage' not in func.pod.spec.labels:
        return

    # 修正提示：这里标记了原实现中需要进一步确认的边界。
    size = parse_size_string(func.pod.spec.labels['data.skippy.io/receives-from-storage'])
    path = func.pod.spec.labels['data.skippy.io/receives-from-storage/path']

    storage_node_name = env.cluster.get_storage_nodes(path)[0]
    logger.debug('%.2f replica %s fetching data %s from %s', env.now, node, path, storage_node_name)

    if storage_node_name == node.name:
        # 修正提示：这里标记了原实现中需要进一步确认的边界。
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(size / 1.25e+8)  
        return

    storage_node = env.cluster.get_node(storage_node_name)
    route = env.topology.route_by_node_name(storage_node.name, node.name)
    flow = SafeFlow(env, size, route)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield flow.start()
    for hop in route.hops:
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        env.metrics.log_network(size, 'data_download', hop)
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'data_download')


def simulate_data_upload(env: Environment, replica: FunctionReplica):
    """
    函数作用：模拟函数把执行结果上传到存储节点。
    关键流程：
    - 通过 env.timeout 推进仿真时间，用真实/经验耗时近似业务阶段延迟。
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    - 涉及网络流或镜像/数据传输，网络耗时会影响仿真时钟。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    node = replica.node.ether_node
    func = replica
    started = env.now

    if 'data.skippy.io/sends-to-storage' not in func.pod.spec.labels:
        return

    # 修正提示：这里标记了原实现中需要进一步确认的边界。
    size = parse_size_string(func.pod.spec.labels['data.skippy.io/sends-to-storage'])
    path = func.pod.spec.labels['data.skippy.io/sends-to-storage/path']

    storage_node_name = env.cluster.get_storage_nodes(path)[0]
    logger.debug('%.2f replica %s uploading data %s to %s', env.now, node, path, storage_node_name)

    if storage_node_name == node.name:
        # 修正提示：这里标记了原实现中需要进一步确认的边界。
        # 仿真推进：等待经验耗时，模拟该生命周期阶段真实经过的时间。
        yield env.timeout(size / 1.25e+8)  
        return

    storage_node = env.cluster.get_node(storage_node_name)
    route = env.topology.route_by_node_name(node.name, storage_node.name)
    flow = SafeFlow(env, size, route)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield flow.start()
    for hop in route.hops:
        # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
        env.metrics.log_network(size, 'data_upload', hop)
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'data_upload')


def simulate_function_invocation(env: Environment, replica: FunctionReplica, request: FunctionRequest):
    """
    函数作用：把数据下载、函数执行和数据上传串联成完整请求调用流程。
    关键流程：
    - 把关键事件写入 Metrics，便于实验结束后统计部署、调度、调用或资源指标。
    - 触发函数调用并等待响应，用于工作负载生成或复合调用流程。
    - 作为 SimPy 协程运行，使用 yield 控制离散事件推进。
    参数：env：仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标和资源状态。；replica：正在部署、执行或释放的函数副本。；request：函数调用请求，包含目标函数名、请求 ID 和数据大小。。
    产出：SimPy 事件序列，调用方通过 yield/env.process 等待该业务阶段完成。
    """
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_start_exec(request, replica)
    # 仿真推进：向 SimPy 事件队列交出控制权。
    yield from replica.simulator.invoke(env, replica, request)
    # 指标记录：把当前业务事件写入结构化结果，便于实验后分析。
    env.metrics.log_stop_exec(request, replica)
