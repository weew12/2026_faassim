# 系统实现

本节说明 faas-sim 中 `FaasSystem` 实现的内部工作机制。`FaasSystem` 的 API 围绕真实系统需求设计，表示典型 API Gateway 中常见的操作，例如 [OpenFaaS](https://docs.openfaas.com/) 中的网关操作。

faas-sim 提供了 `FaasSystem` 的默认实现，即 `sim.faas.system.py` 中的 `DefaultFaasSystme`。本节解释该实现的内部工作方式、涉及的组件以及用户可以如何配置系统。

`FaasSystem` 需要实现的方法如下：

```python
class FaasSystem(abc.ABC):

    def deploy(self, fn: FunctionDeployment): ...

    def invoke(self, request: FunctionRequest): ...

    def remove(self, fn: FunctionDeployment): ...

    def discover(self, fn_name: str) -> List[FunctionReplica]: ...

    def scale_down(self, fn_name: str, remove: int): ...

    def scale_up(self, fn_name: str, replicas: int): ...

    def suspend(self, fn_name: str): ...

    # 以及若干额外查询方法
```

为了实现这些函数，DefaultFaasSystem 维护如下内部状态。

> 注意：本节描述的是当前 `FaasSystem` 实现的内部细节，后续版本可能发生变化。为了降低兼容性风险，外部代码应优先使用公开查询方法，而不是直接依赖内部字段。

- `env: Environment`：用于访问全局配置组件，例如 `Metrics`、`SimulatorFactory` 和 `ClusterContext`。
- `function_containers: Dict[str, FunctionContainer]`：存储已部署函数中所有可用的函数容器。
- `replicas: Dict[str, List[FunctionReplica]]`：按照 FunctionDeployment 名称收集对应的 FunctionReplica 列表。
- `scheduler_queue: simpy.Store`：保存需要被调度的函数副本。`scale_up` 会将副本放入队列，`run_schedule_worker` 会从队列中轮询取出副本并执行调度。
- `load_balancer: LoadBalancer`：在 `invoke` 过程中被调用，用于选择处理本次调用的函数副本。目前默认实现为 round-robin。
- `functions_deployments: Dict[str, FunctionDeployment]`：存储已部署函数，主要由 `deploy` 和 `remove` 修改。
- `replica_count: Dict[str, int]`：统计每个 FunctionDeployment 当前活跃副本数量。
- `functions_definitions: Counter`：统计每个 FunctionContainer 对应的副本数量。

## Resources

由于 `FunctionSimulator` 具有很高的灵活性，资源仿真需要由用户根据具体模型实现。例如，函数执行可能受到排队机制影响，因此资源并不一定在请求到达时立即消耗，而应由 `FunctionSimulator` 在恰当的时间点声明资源使用。

faas-sim 提供了一套基于字典的标准资源管理接口。这一接口允许 faas-sim 实现通用组件，例如节点与函数资源监控，以及 [Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) 的实现。资源值会按键累加。

下面的代码展示了一个消耗资源的示例：

```python
class CpuConsumingSim(FunctionSimulator):

    def __init__(self, queue: simpy.Resource):
        self.queue = queue

    def invoke(self, env: Environment, replica: FunctionReplica, request: FunctionRequest):
        token = self.queue.request()
        yield token

        # 资源定义由用户决定。
        # 这里假设一次函数调用在整个调用期间需要占用 20% CPU。
        env.resource_state.put_resource(replica, 'cpu', 0.2)

        yield env.timeout(1)

        # 调用结束后释放资源。
        env.resource_state.remove_resource(replica, 'cpu', 0.2)
```

`Environment` 对象包含 resource monitor。该监控器会持续收集当前资源利用率，并将数据写入 `MetricsServer`。随后，用户可以通过 `MetricsServer` 查询某类资源在指定时间范围内的平均使用情况。
