"""
默认 FaaS 平台实现。

DefaultFaasSystem 串联函数部署、副本创建、调度队列、请求转发、扩缩容、挂起、删除和生命周期模拟，是 faas-sim 业务层最关键的运行时组件。

阅读建议：按 deploy -> scale_up -> run_scheduler_worker -> simulate_function_start -> invoke 的顺序阅读。
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

logger = logging.getLogger(__name__)


class DefaultFaasSystem(FaasSystem):
    """
    默认 FaaS 平台实现。

    负责函数部署、副本创建、调度队列、请求路由、扩缩容、挂起、删除和生命周期模拟，是业务层核心运行时。

    重要字段：
    - env: 全局仿真环境，提供 SimPy 时钟、拓扑、FaaS 系统、指标器和资源状态等上下文。
    - function_containers: 镜像字符串到 FunctionContainer 的索引。
    - replicas: 函数名到副本列表的映射，记录平台当前已创建的副本。
    - request_queue: 请求队列对象，保留给请求排队模型使用。
    - scheduler_queue: 待调度副本队列，deploy_replica 会把副本放入这里等待调度 worker 处理。
    - load_balancer: 负载均衡器，负责在多个 RUNNING 副本之间选择请求目标。
    - functions_deployments: 函数名到 FunctionDeployment 的索引。
    - replica_count: 函数名到副本数量的映射，用于快速判断当前规模。
    - functions_definitions: 容器镜像被部署次数的计数器。
    - scale_by_requests: 是否启用基于请求数量的伸缩策略。
    - scale_by_average_requests_per_replica: 是否启用基于平均每副本 RPS 的伸缩策略。
    - scale_by_queue_requests_per_replica: 是否启用基于队列长度的伸缩策略。
    - faas_scalers: 基于请求数量的伸缩器索引。
    - avg_faas_scalers: 基于平均每副本 RPS 的伸缩器索引。
    - queue_faas_scalers: 基于每副本队列长度的伸缩器索引。

    阅读提示：先确认这些字段在哪个阶段被初始化，再沿公开方法查看它们如何驱动调度、执行、监控或统计流程。
    """

    
    def __init__(self, env: Environment, scale_by_requests: bool = False,
                 scale_by_average_requests: bool = False, scale_by_queue_requests_per_replica: bool = False) -> None:
        """
        初始化 DefaultFaasSystem 对象。

        主要建立字段：env、function_containers、replicas、request_queue、scheduler_queue、load_balancer、functions_deployments、replica_count、functions_definitions、scale_by_requests、scale_by_average_requests_per_replica、scale_by_queue_requests_per_replica、faas_scalers、avg_faas_scalers、queue_faas_scalers。这些字段构成对象后续参与部署、调度、执行、监控或指标记录时需要的内部状态。

        参数说明：
        - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
        - scale_by_requests: scale_by_requests 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：bool。
        - scale_by_average_requests: scale_by_average_requests 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：bool。
        - scale_by_queue_requests_per_replica: scale_by_queue_requests_per_replica 参数，参与当前方法的计算、查询、状态更新或流程控制。 类型标注：bool。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        self.env = env
        self.function_containers = dict()
        
        self.replicas = defaultdict(list)

        self.request_queue = simpy.Store(env)
        self.scheduler_queue = simpy.Store(env)

        self.load_balancer = RoundRobinLoadBalancer(env, self.replicas)

        self.functions_deployments: Dict[str, FunctionDeployment] = dict()
        self.replica_count: Dict[str, int] = dict()
        self.functions_definitions = Counter()

        self.scale_by_requests = scale_by_requests
        self.scale_by_average_requests_per_replica = scale_by_average_requests
        self.scale_by_queue_requests_per_replica = scale_by_queue_requests_per_replica
        self.faas_scalers: Dict[str, FaasRequestScaler] = dict()
        self.avg_faas_scalers: Dict[str, AverageFaasRequestScaler] = dict()
        self.queue_faas_scalers: Dict[str, AverageQueueFaasRequestScaler] = dict()

    def get_deployments(self) -> List[FunctionDeployment]:
        """
        返回当前平台中已经登记的函数部署列表。

        伸缩器、资源监控器和实验代码会通过该方法遍历所有函数。

        返回说明：返回值类型标注为 List[FunctionDeployment]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return list(self.functions_deployments.values())

    def get_function_index(self) -> Dict[str, FunctionContainer]:
        """
        返回镜像到 FunctionContainer 的索引。

        调度器创建 Pod 或查找容器资源需求时会使用这个映射。

        返回说明：返回值类型标注为 Dict[str, FunctionContainer]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.function_containers

    def get_replicas(self, fn_name: str, state=None) -> List[FunctionReplica]:
        """
        按函数名读取副本列表，可选择按状态过滤。

        state 为 None 时返回该函数的全部副本；传入 FunctionState.RUNNING 等状态时只返回匹配副本。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - state: 副本生命周期状态过滤条件。

        返回说明：返回值类型标注为 List[FunctionReplica]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        if state is None:
            return self.replicas[fn_name]

        return [replica for replica in self.replicas[fn_name] if replica.state == state]

    def deploy(self, fd: FunctionDeployment):
        """
        部署一个函数并启动必要的伸缩控制器。

        流程包括检查重名、登记部署和容器索引、创建 RPS/平均 RPS/队列伸缩器、写入部署指标，并按 scale_min 创建初始副本。

        参数说明：
        - fd: FunctionDeployment，描述一个函数的定义、容器、伸缩配置和镜像排序。 类型标注：FunctionDeployment。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：典型调用路径是 Benchmark.run -> env.faas.deploy -> scale_up -> deploy_replica -> scheduler_queue。
        """
        if fd.name in self.functions_deployments:
            raise ValueError('function already deployed')

        # 1. 先登记部署对象和伸缩器。此时还没有真实副本，只是把函数加入平台控制面。
        self.functions_deployments[fd.name] = fd
        self.faas_scalers[fd.name] = FaasRequestScaler(fd, self.env)
        self.avg_faas_scalers[fd.name] = AverageFaasRequestScaler(fd, self.env)
        self.queue_faas_scalers[fd.name] = AverageQueueFaasRequestScaler(fd, self.env)

        # 2. 根据构造参数决定启动哪类后台伸缩控制器。
        # 这些进程不会阻塞 deploy，会在仿真过程中周期性读取 metrics 并触发扩缩容。
        if self.scale_by_requests:
            self.env.process(self.faas_scalers[fd.name].run())
        if self.scale_by_average_requests_per_replica:
            self.env.process(self.avg_faas_scalers[fd.name].run())
        if self.scale_by_queue_requests_per_replica:
            self.env.process(self.queue_faas_scalers[fd.name].run())

        # 3. 建立镜像 -> 容器规格索引，后续调度、调用指标和资源需求查询都会用到。
        for f in fd.fn_containers:
            self.function_containers[f.image] = f

        self.env.metrics.log_function_deployment(fd)
        self.env.metrics.log_function_deployment_lifecycle(fd, 'deploy')
        logger.info('deploying function %s with scale_min=%d', fd.name, fd.scaling_config.scale_min)
        # 4. deploy 的最后一步不是直接启动容器，而是按 scale_min 创建初始副本并送入调度队列。
        yield from self.scale_up(fd.name, fd.scaling_config.scale_min)

    def deploy_replica(self, fd: FunctionDeployment, fn: FunctionContainer, services: List[FunctionContainer]):
        """
        创建一个函数副本并放入调度队列。

        副本先进入 replicas 索引并记录调度指标，随后以 (replica, services) 的形式交给 scheduler_queue，等待调度器选择节点。

        参数说明：
        - fd: FunctionDeployment，描述一个函数的定义、容器、伸缩配置和镜像排序。 类型标注：FunctionDeployment。
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionContainer。
        - services: 候选容器列表；当前镜像调度失败时可继续尝试后续服务。 类型标注：List[FunctionContainer]。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：这是副本从“期望创建”进入“等待调度”的入口，真正启动发生在 run_scheduler_worker。
        """
        replica = self.create_replica(fd, fn)
        self.replicas[fd.name].append(replica)
        self.env.metrics.log_queue_schedule(replica)
        self.env.metrics.log_function_replica(replica)
        # scheduler_queue 是控制面和调度器之间的边界：put 之后由 run_scheduler_worker 异步处理。
        yield self.scheduler_queue.put((replica, services))

    def invoke(self, request: FunctionRequest):
        """
        处理一次函数调用请求。

        若函数不存在则直接返回；若没有运行中副本，则等待 scale-from-zero 或部署流程产生可用副本；随后通过负载均衡器选择副本，执行函数调用并记录等待时间和执行时间。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：典型调用路径是 requestgen.function_trigger -> env.faas.invoke -> simulate_function_invocation -> replica.simulator.invoke。
        """
        logger.debug('invoking function %s', request.name)

        if request.name not in self.functions_deployments.keys():
            logger.warning('invoking non-existing function %s', request.name)
            return

        t_received = self.env.now

        replicas = self.get_replicas(request.name, FunctionState.RUNNING)
        if not replicas:
            # 没有可用副本时，调用方会在这里等待副本进入 RUNNING。
            # 如果外部启用了 scale-to-zero，扩容逻辑应该在等待期间创建最小副本。
            '''
            https://docs.openfaas.com/architecture/autoscaling/#scaling-up-from-zero-replicas

            When scale_from_zero is enabled a cache is maintained in memory indicating the readiness of each function.
            If when a request is received a function is not ready, then the HTTP connection is blocked, the function is
            scaled to min replicas, and as soon as a replica is available the request is proxied through as per normal.
            You will see this process taking place in the logs of the gateway component.
            '''
            yield from self.poll_available_replica(request.name)

        if len(replicas) < 1:
            raise ValueError
        elif len(replicas) > 1:
            logger.debug('asking load balancer for replica for request %s:%d', request.name, request.request_id)
            # 多副本场景下只把 RUNNING 副本交给负载均衡器，避免把请求发到未启动或已挂起副本。
            replica = self.next_replica(request)
        else:
            replica = replicas[0]

        logger.debug('dispatching request %s:%d to %s', request.name, request.request_id, replica.node.name)

        # t_received -> t_start 是排队/等待可用副本的时间；t_start -> t_end 是实际调用路径耗时。
        t_start = self.env.now
        yield from simulate_function_invocation(self.env, replica, request)

        t_end = self.env.now

        t_wait = t_start - t_received
        t_exec = t_end - t_start
        self.env.metrics.log_invocation(request.name, replica.image, replica.node.name, t_wait, t_start,
                                        t_exec, id(replica))

    def remove(self, fn: FunctionDeployment):
        """
        删除一个函数部署。

        先记录删除生命周期事件，再缩容所有副本、停止该函数的伸缩器，并清理部署表、伸缩器表、计数器和函数定义索引。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionDeployment。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        self.env.metrics.log_function_deployment_lifecycle(fn, 'remove')

        replica_count = self.replica_count[fn.name]
        yield from self.scale_down(fn.name, replica_count)
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
        按数量缩减函数副本。

        方法会遵守 scale_min 下限，只从 RUNNING 副本中选择要删除的实例，记录缩容指标，并逐个执行副本移除流程。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - remove: 希望减少的副本数量。 类型标注：int。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：缩容会改变副本生命周期状态并调用 teardown，指标中的负数 scale 表示减少副本。
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
        self.env.metrics.log_scaling(fn_name, -remove)
        for replica in replicas:
            yield from self._remove_replica(replica)
            replicas.remove(replica)

    def choose_replicas_to_remove(self, fn_name: str, n: int):
        """
        选择待删除副本。

        当前策略从运行中副本列表尾部取 n 个，等价于优先删除最近追加到列表末尾的副本。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - n: 需要选择或处理的数量。 类型标注：int。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        running_replicas = self.get_replicas(fn_name, FunctionState.RUNNING)
        return running_replicas[len(running_replicas) - n:]

    def scale_up(self, fn_name: str, replicas: int):
        """
        按数量扩展函数副本。

        方法会遵守 scale_max 上限，并按 deployment ranking 中的服务顺序创建副本。每个副本创建后会进入调度队列，等待节点调度和生命周期启动。

        参数说明：
        - fn_name: 目标函数名。 类型标注：str。
        - replicas: 副本数量或副本列表，具体由所在方法决定。 类型标注：int。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：扩容只创建和排队副本，副本能否运行取决于后续调度和启动流程。
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

        if self.replica_count[fn_name] + replicas > config.scale_max:
            reduce = self.replica_count[fn_name] + replicas - config.scale_max
            scale = replicas - reduce

        if scale == 0:
            return
        actually_scaled = 0
        for index, service in enumerate(fd.get_services()):
            
            leftover_scale = scale
            max_replicas = int(ranking.function_factor[service.image] * config.scale_max)

            # function_factor 用于限制某个镜像/服务在总副本中的占比。
            # 当首选服务达到比例上限时，剩余副本会继续尝试后面的服务。
            
            if max_replicas * config.scale_max < leftover_scale + self.functions_definitions[
                service.image]:

                
                reduce = max_replicas - self.functions_definitions[service.image]
                if reduce < 0:
                    
                    continue
                leftover_scale = leftover_scale - reduce
            if leftover_scale > 0:
                for _ in range(leftover_scale):
                    yield from self.deploy_replica(fd, fd.get_container(service.image), fd.get_containers()[index:])
                    actually_scaled += 1
                    scale -= 1

        self.env.metrics.log_scaling(fd.name, actually_scaled)

        if scale > 0:
            logger.debug("Function %s wanted to scale, but not all requested replicas were deployed: %s", fn_name,
                         str(scale))

    def next_replica(self, request) -> FunctionReplica:
        """
        为请求选择下一个运行副本。

        默认实现委托 RoundRobinLoadBalancer，在同一函数的 RUNNING 副本之间轮询分配请求。

        参数说明：
        - request: FunctionRequest，表示一次待处理的函数调用。

        返回说明：返回值类型标注为 FunctionReplica，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return self.load_balancer.next_replica(request)

    def start(self):
        """
        启动 FaaS 系统后台工作进程。

        当前主要启动调度 worker，使 scheduler_queue 中的副本能够被持续调度。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        for process in self.env.background_processes:
            self.env.process(process(self.env))
        self.env.process(self.run_scheduler_worker())

    def poll_available_replica(self, fn: str, interval=0.5):
        """
        轮询等待函数出现可用副本。

        每隔 interval 仿真时间检查一次 RUNNING 副本；如果配置允许 scale_zero，会先触发 scale_min 数量的扩容。

        参数说明：
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：str。
        - interval: 轮询或后台循环间隔，单位为仿真时间。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        while not self.get_replicas(fn, FunctionState.RUNNING):
            yield self.env.timeout(interval)

    def run_scheduler_worker(self):
        """
        SimPy 协程：run_scheduler_worker。

        函数中的 yield/yield from 会把控制权交还给仿真环境；调用方应使用 yield from 等待完成，或使用 env.process(...) 作为后台进程启动。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

        业务流程：该 worker 长期运行，是 scheduler_queue 到 simulate_function_start 的桥梁。
        """
        env = self.env

        while True:
            replica: FunctionReplica
            # worker 在这里阻塞等待 deploy_replica 放入的新副本。
            replica, services = yield self.scheduler_queue.get()

            logger.debug('scheduling next replica %s', replica.function.name)

            # 调度耗时使用真实 wall clock 测量，再映射成仿真时间延迟。
            # 这样可以把调度算法本身的计算成本也计入实验时间线。
            self.env.metrics.log_start_schedule(replica)
            pod = replica.pod
            then = time.time()
            result = env.scheduler.schedule(pod)
            duration = time.time() - then
            self.env.metrics.log_finish_schedule(replica, result)

            yield env.timeout(duration)  

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('Pod scheduling took %.2f ms, and yielded %s', duration * 1000, result)

            if not result.suggested_host:
                self.replicas[replica.fn_name].remove(replica)
                if len(services) > 0:
                    # 当前镜像无法调度时，尝试同一函数的下一个候选容器/镜像。
                    logger.warning('retry scheduling pod %s', pod.name)
                    yield from self.deploy_replica(replica.function, services[0], services[1:])
                else:
                    logger.error('pod %s cannot be scheduled', pod.name)

                continue

            logger.info('pod %s was scheduled to %s', pod.name, result.suggested_host)

            # 调度结果只包含 Skippy 节点；这里把它转回 faas-sim 的 NodeState。
            replica.node = self.env.get_node_state(result.suggested_host.name)
            node = replica.node.skippy_node

            # 记录调度后节点已分配比例，用于观察调度策略是否导致资源热点。
            env.metrics.log('allocation', {
                'cpu': 1 - (node.allocatable.cpu_millis / node.capacity.cpu_millis),
                'mem': 1 - (node.allocatable.memory / node.capacity.memory)
            }, node=node.name)

            self.functions_definitions[replica.image] += 1
            self.replica_count[replica.fn_name] += 1

            self.env.metrics.log_function_deploy(replica)
            
            # 副本启动耗时不阻塞调度 worker；worker 可以继续调度后续副本。
            env.process(simulate_function_start(env, replica))

    def create_pod(self, fd: FunctionDeployment, fn: FunctionContainer):
        """
        为函数容器创建调度 Pod。

        默认委托 create_function_pod，子类可覆盖以加入额外标签或资源需求。

        参数说明：
        - fd: FunctionDeployment，描述一个函数的定义、容器、伸缩配置和镜像排序。 类型标注：FunctionDeployment。
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionContainer。

        返回说明：返回当前方法的查询、计算或创建结果；调用方通常会继续把它用于调度、执行、统计或条件判断。
        """
        return create_function_pod(fd, fn)

    def create_replica(self, fd: FunctionDeployment, fn: FunctionContainer) -> FunctionReplica:
        """
        根据部署和容器规格创建 FunctionReplica。

        方法会为副本绑定 FunctionDeployment、FunctionContainer、Pod 和专属 FunctionSimulator。此时副本还没有被调度到节点。

        参数说明：
        - fd: FunctionDeployment，描述一个函数的定义、容器、伸缩配置和镜像排序。 类型标注：FunctionDeployment。
        - fn: 函数部署、函数容器或函数名，具体含义由调用位置决定。 类型标注：FunctionContainer。

        返回说明：返回值类型标注为 FunctionReplica，通常作为后续调度、执行、统计或查询流程的输入。
        """
        replica = FunctionReplica()
        replica.function = fd
        replica.container = fn
        replica.pod = self.create_pod(fd, fn)
        replica.simulator = self.env.simulator_factory.create(self.env, fn)
        return replica

    def discover(self, function: str) -> List[FunctionReplica]:
        """
        查找某个容器镜像对应的所有可运行副本。

        该方法遍历全部部署副本，筛选镜像相同且状态为 RUNNING 的副本，用于服务发现和路由。

        参数说明：
        - function: 函数名或函数容器，具体由方法签名决定。 类型标注：str。

        返回说明：返回值类型标注为 List[FunctionReplica]，通常作为后续调度、执行、统计或查询流程的输入。
        """
        return [replica for replica in self.replicas[function] if replica.state == FunctionState.RUNNING]

    def _remove_replica(self, replica: FunctionReplica):
        """
        执行单个副本的下线流程。

        将副本从 RUNNING 变为 SUSPENDED，调用 simulator.teardown 释放运行时资源，并维护副本列表与副本计数。

        参数说明：
        - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

        协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
        """
        env = self.env
        node = replica.node.skippy_node

        env.metrics.log_teardown(replica)
        yield from replica.simulator.teardown(env, replica)

        self.env.cluster.remove_pod_from_node(replica.pod, node)
        replica.state = FunctionState.SUSPENDED
        self.replicas[replica.function.name].remove(replica)

        env.metrics.log('allocation', {
            'cpu': 1 - (node.allocatable.cpu_millis / node.capacity.cpu_millis),
            'mem': 1 - (node.allocatable.memory / node.capacity.memory)
        }, node=node.name)
        self.replica_count[replica.fn_name] -= 1
        self.functions_definitions[replica.image] -= 1

    def suspend(self, function_name: str):
        """
        挂起指定函数的所有运行副本。

        副本状态会被标记为 SUSPENDED，后续不会再被负载均衡器选中。

        参数说明：
        - function_name: 目标函数名。 类型标注：str。

        返回说明：无显式返回值，主要通过修改对象状态、写入队列、记录指标或推进仿真事件产生影响。
        """
        if function_name not in self.functions_deployments.keys():
            raise ValueError

        replicas: List[FunctionReplica] = self.discover(function_name)
        # 伸缩动作：根据当前观测结果调整函数副本数量。
        self.scale_down(function_name, len(replicas))

        self.env.metrics.log_function_deployment_lifecycle(self.functions_deployments[function_name], 'suspend')


def simulate_function_start(env: Environment, replica: FunctionReplica):
    """
    模拟函数副本从调度完成到可运行的启动流程。

    流程依次设置节点和 Pod、记录调度延迟、拉取镜像、执行 simulator.deploy/startup/setup，并在结束后把状态切换为 RUNNING。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

    业务流程：该协程把“调度成功的副本”推进为 RUNNING 副本。
    """
    sim: FunctionSimulator = replica.simulator

    # deploy 阶段通常负责镜像拉取或容器创建。不同 FunctionSimulator 可以覆盖具体耗时模型。
    logger.debug('deploying function %s to %s', replica.function.name, replica.node.name)
    env.metrics.log_deploy(replica)
    yield from sim.deploy(env, replica)

    # startup/setup 分开记录，便于实验后区分平台启动耗时和函数运行时准备耗时。
    replica.state = FunctionState.STARTING
    env.metrics.log_startup(replica)
    logger.debug('starting function %s on %s', replica.function.name, replica.node.name)
    yield from sim.startup(env, replica)

    logger.debug('running function setup %s on %s', replica.function.name, replica.node.name)
    env.metrics.log_setup(replica)
    yield from sim.setup(env, replica)
    env.metrics.log_finish_deploy(replica)
    # 只有 setup 完成后才允许负载均衡器选择该副本处理请求。
    replica.state = FunctionState.RUNNING


def simulate_data_download(env: Environment, replica: FunctionReplica):
    """
    模拟请求输入数据下载。

    若请求声明了 size，则在客户端节点和副本节点之间建立 SafeFlow，用网络带宽决定下载耗时；没有 size 时不产生网络延迟。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    node = replica.node.ether_node
    func = replica
    started = env.now

    if 'data.skippy.io/receives-from-storage' not in func.pod.spec.labels:
        return

    # 数据大小和路径来自 Pod label，这让样例或扩展模拟器可以不改核心代码就声明数据依赖。
    size = parse_size_string(func.pod.spec.labels['data.skippy.io/receives-from-storage'])
    path = func.pod.spec.labels['data.skippy.io/receives-from-storage/path']

    storage_node_name = env.cluster.get_storage_nodes(path)[0]
    logger.debug('%.2f replica %s fetching data %s from %s', env.now, node, path, storage_node_name)

    if storage_node_name == node.name:
        # 数据就在本节点时不走拓扑链路，按本地默认带宽估计读取耗时。
        yield env.timeout(size / 1.25e+8)  
        return

    # 跨节点下载通过 SafeFlow 建模，链路级 network 和端到端 flow 两类指标都会记录。
    storage_node = env.cluster.get_node(storage_node_name)
    route = env.topology.route_by_node_name(storage_node.name, node.name)
    flow = SafeFlow(env, size, route)
    yield flow.start()
    for hop in route.hops:
        env.metrics.log_network(size, 'data_download', hop)
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'data_download')


def simulate_data_upload(env: Environment, replica: FunctionReplica):
    """
    模拟函数响应数据上传。

    该流程与下载方向相反，用同一个 SafeFlow 模型估计从副本节点到客户端节点的传输时间。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。
    """
    node = replica.node.ether_node
    func = replica
    started = env.now

    if 'data.skippy.io/sends-to-storage' not in func.pod.spec.labels:
        return

    # 上传和下载使用同一套 label 约定，只是网络方向相反。
    size = parse_size_string(func.pod.spec.labels['data.skippy.io/sends-to-storage'])
    path = func.pod.spec.labels['data.skippy.io/sends-to-storage/path']

    storage_node_name = env.cluster.get_storage_nodes(path)[0]
    logger.debug('%.2f replica %s uploading data %s to %s', env.now, node, path, storage_node_name)

    if storage_node_name == node.name:
        # 目标存储节点就是当前节点时，按本地默认带宽估计写入耗时。
        yield env.timeout(size / 1.25e+8)  
        return

    # 跨节点上传会沿副本节点 -> 存储节点方向记录链路流量。
    storage_node = env.cluster.get_node(storage_node_name)
    route = env.topology.route_by_node_name(node.name, storage_node.name)
    flow = SafeFlow(env, size, route)
    yield flow.start()
    for hop in route.hops:
        env.metrics.log_network(size, 'data_upload', hop)
    env.metrics.log_flow(size, env.now - started, route.source, route.destination, 'data_upload')


def simulate_function_invocation(env: Environment, replica: FunctionReplica, request: FunctionRequest):
    """
    模拟一次完整函数调用。

    当前核心实现负责记录执行开始/结束指标，并委托 replica.simulator.invoke() 表达函数主体耗时。
    数据下载和上传由具体 FunctionSimulator 或扩展模拟器显式调用 simulate_data_download()/simulate_data_upload()，
    因此这里不会默认给所有请求叠加网络传输。

    参数说明：
    - env: 仿真环境，提供当前仿真时间、事件调度和全局业务组件。 类型标注：Environment。
    - replica: FunctionReplica，表示某个函数在某个节点上的运行副本。 类型标注：FunctionReplica。
    - request: FunctionRequest，表示一次待处理的函数调用。 类型标注：FunctionRequest。

    协程行为：该函数包含 yield/yield from，调用后不会一次性完成；它会把控制权交还给 SimPy，由仿真时钟决定后续继续执行的时间。

    业务流程：该协程是默认请求执行包装层；具体执行、资源申请、网络传输通常由副本 simulator 决定。
    """
    # start/stop_exec 主要维护调用计数、last_invocation 和可选指标，供伸缩器与实验分析使用。
    env.metrics.log_start_exec(request, replica)
    yield from replica.simulator.invoke(env, replica, request)
    env.metrics.log_stop_exec(request, replica)
