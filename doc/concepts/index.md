# 核心概念

## 领域模型

faas-sim 对函数、函数部署以及运行中的函数实例建立了统一的概念模型。该模型用于把真实 FaaS 平台中的函数抽象、容器镜像、部署配置、运行实例和集群节点映射到仿真环境中。

![函数及其部署的概念模型](../figures/function-conceptual-view.png)

上图展示了函数及其部署过程中的核心概念关系。

## Function

Function 是最高层次的抽象，表示一个由名称标识、可以通过 FunctionRequest 调用的功能单元。

例如，一个名为 `detect-objects` 的目标检测函数可以接收图像作为输入，并返回图像中对象的边界框和标签。一个 Function 由多个 FunctionImage 组成，每个 FunctionImage 对应一种部署平台或运行实现。

## FunctionImage

FunctionImage 在概念上表示某个函数在特定部署平台上的代码实现。

例如，`detect-objects` 函数可以有一个使用 GPU 的版本，也可以有一个使用 TPU 等 AI 加速器的版本。引入 FunctionImage 这一额外抽象，原因在于 Docker 等容器平台对多计算架构镜像的处理方式。不同 CPU 架构的 Docker 镜像可以通过 [multi-arch manifest](https://docs.docker.com/registry/spec/manifest-v2-2/) 组织到同一个多架构镜像中，`docker pull` 会根据节点架构拉取对应镜像。

但是，Docker 的多架构机制无法表达 GPU、TPU 等额外平台特征。如果同一个函数存在 CPU 镜像和 GPU 镜像，那么运行时可能无法明确应该拉取哪一个镜像。faas-sim 希望将这一决策交给资源调度器，使调度器能够决定某个函数在特定节点上应部署哪个镜像。

## FunctionDeployment

FunctionDeployment 表示 Function 的一个具体部署实例，包含资源分配配置和伸缩策略配置。一个部署由多个 FunctionContainer 以及相关配置组成。

## FunctionContainer

FunctionContainer 是 FunctionImage 的运行时配置。它包含具体的资源配置，用于声明某个 FunctionContainer 的副本部署到节点上时需要分配多少资源。

在前面的目标检测示例中，基于 GPU 的 `object-detector` 可能需要较少 CPU，但需要更多显存；而基于 CPU 的 FunctionImage 则可能需要更多 CPU 资源。

## FunctionReplica

FunctionReplica 是 FunctionContainer 的具体实例化结果，表示真实正在运行的函数实例，类似于 Docker 容器中的一个运行容器。

## Node

Node 表示集群中能够承载函数副本的计算机或计算节点。NodeState 是一个通用的数据容器，用于存储仿真运行时需要的数据。例如，为了计算性能退化，可以在 NodeState 中记录某个函数副本当前并发调用数量。

## FaaS System

`FaasSystem` 抽象是客户端交互的高层接口。可以将它理解为 OpenFaaS 中的主 API Gateway，或者 Kubernetes 中的 kube-apiserver。

其接口形式如下：

```python
class FaasSystem(abc.ABC):

    def deploy(self, fn: FunctionDeployment): ...

    def invoke(self, request: FunctionRequest): ...

    def remove(self, fn: FunctionDeployment): ...

    def suspend(self, fn_name: str): ...

    def discover(self, fn_name: str) -> List[FunctionReplica]: ...

    def scale_down(self, fn_name: str, remove: int): ...

    def scale_up(self, fn_name: str, replicas: int): ...

    # 额外查询方法：
    def poll_available_replica(self, fn: str, interval=0.5): ...

    def get_replicas(self, fn_name: str, state=None) -> List[FunctionReplica]: ...

    def get_function_index(self) -> Dict[str, FunctionContainer]: ...

    def get_deployments(self) -> List[FunctionDeployment]: ...
```

从概念上看，FaaS System 的主要阶段和接口含义如下。

- `deploy`：使函数变为可调用状态，并在集群上部署最小数量的 FunctionReplica。最小运行实例数量由 `ScalingConfiguration` 配置。
- `invoke`：由 `LoadBalancer` 选择一个副本，然后调用该副本关联的 `FunctionSimulator.invoke` 方法来模拟函数调用。
- `remove`：从平台中删除函数，并关闭所有正在运行的副本。
- `discover`：返回属于某个函数的所有运行中 FunctionReplica。
- `scale_down`：在不低于最小副本数要求的前提下，移除指定数量的运行中 FunctionReplica。当前实现优先选择最近部署的副本进行移除。
- `scale_up`：部署指定数量的 FunctionReplica，但必须遵守 `ScalingConfiguration` 中定义的最大副本数。
- `suspend`：对某个函数的所有运行中副本执行 teardown，常用于 `faas_idler`。
- `poll_available_replica`：反复等待并检查某个函数是否存在运行中的副本。
- `get_replicas`：获取某个函数在指定状态下的所有副本；当 `state == None` 时返回全部副本。
- `get_function_index`：返回所有已部署的 FunctionContainer。
- `get_deployments`：返回所有已部署的 FunctionDeployment 实例。

## Function simulators

FunctionSimulator 封装了函数的仿真代码，是 faas-sim 的核心抽象之一。faas-sim 内置了若干函数仿真器，它们以真实函数和真实工作负载的 trace 数据为基础执行仿真。

FunctionSimulator 的方法由仿真器调用，用于模拟函数生命周期中的不同阶段。

```python
class FunctionSimulator(abc.ABC):
    def deploy(self, env: Environment, replica: FunctionReplica):
        yield env.timeout(0)

    def startup(self, env: Environment, replica: FunctionReplica):
        yield env.timeout(0)

    def setup(self, env: Environment, replica: FunctionReplica):
        yield env.timeout(0)

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        yield env.timeout(0)

    def teardown(self, env: Environment, replica: FunctionReplica):
        yield env.timeout(0)
```

从概念上看，FunctionSimulator 的生命周期阶段包括：

- `deploy`：FunctionReplica 被部署到节点上，例如通过 `docker pull` 拉取容器镜像。
- `startup`：副本启动过程，例如通过 `docker run` 启动容器。
- `setup`：副本运行时启动过程，例如 Python Runtime 启动解释器、加载依赖或初始化模型。
- `invoke`：某个 FunctionRequest 调用具体的函数副本。
- `teardown`：函数副本被销毁，例如由于 scale down 而被移除。

每当仿真器因为部署或伸缩动作创建新的函数副本时，SimulatorFactory 会被调用，用于创建或返回该副本对应的 FunctionSimulator。SimulatorFactory 可以被用户覆盖，从而实现多种行为：每次返回同一个 FunctionSimulator、为每个函数副本创建新实例，或根据函数、节点、镜像等上下文选择不同仿真器。

关于函数仿真器的更多细节，可继续阅读 [函数仿真器](../function_sims/index.md) 和项目中的示例代码。

## Simulation

Simulation 封装了一次仿真的配置和运行时状态。一次 Simulation 需要两个输入：Topology 和 Benchmark。

### Topology

Topology 包装 [Ether](https://github.com/edgerun/ether) 拓扑，用于表示集群配置和网络拓扑。

### Benchmark

Benchmark 封装一个具体的仿真实验。它作为 SimPy 进程被调用，负责设置运行时系统，例如创建容器镜像、部署函数，并通过模拟函数请求生成工作负载。

faas-sim 提供了若干工具用于创建 Benchmark，例如请求生成器。Benchmark 包含两个方法：`setup` 和 `run`。

当仿真环境创建完成后，系统会调用 `setup` 方法。用户可以在该方法中准备被测系统，例如向模拟容器仓库中注册镜像。随后，`run` 方法会作为主 SimPy 进程被调用，仿真会一直运行到该进程结束。

## Request generators

Request generator 是用于创建工作负载生成器的可组合函数。使用示例如下：

```python
from sim.requestgen import expovariate_arrival_profile, constant_rps_profile

env = ...
gen = expovariate_arrival_profile(constant_rps_profile(20))

while True:
    ia = next(gen)
    yield env.timeout(ia)
    # 发送下一个请求
```

下图展示了若干到达过程和工作负载模式组合后的请求模式。

![到达过程与工作负载模式组合示例](../figures/workload-generators.png)

上图展示了如何组合 inter-arrival distribution 与 workload pattern 来生成工作负载。

第一行展示了如何构造随机化的正弦请求模式。对于 interarrival distribution，示例使用指数分布。指数分布的概率密度函数为 \(\lambda e^{-\lambda x}\)，其中 \(\frac{1}{\lambda}\) 是均值。工作负载模式遵循正弦波，并使用 \(\sin(t)\) 的值作为 \(\lambda\)，从而缩放 interarrival distribution。

因此，在仿真时，系统会从分布 \(\sin(t)e^{-\sin(t)x}\) 中采样，以得到下一次请求到来前的等待时间。图中的橙色线表示请求每秒数量的移动平均值，它应大致匹配工作负载模式。

第二行展示了 constant interarrival distribution 如何精确复制工作负载模式，以及 constant workload profile 如何与 expovariate distribution 组合，形成具有随机到达间隔的静态负载模式。

最后一行展示了 Gaussian random walks（GRW）。其中每个值表示从正态分布中采样得到的随机样本，并作为下一次随机采样中的 \(\mu\) 值。请求 profile 可以通过 \(\sigma\) 参数控制随时间波动的幅度。

提示：可以在项目的 Jupyter Notebook `workload_patterns.ipynb` 中找到生成这些模式的代码示例，也可以查看 `examples/request_gen` 下的仿真示例。
