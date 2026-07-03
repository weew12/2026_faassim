# 函数仿真器

本节展示 faas-sim 中一部分预定义 FunctionSimulator，并说明如何自行实现 FunctionSimulator。

> 注意：阅读本节前，建议先熟悉 [Resources](../system/index.md#resources) 和 [Function simulators](../concepts/index.md#function-simulators) 两部分内容。

faas-sim 的设计和架构受到 [OpenFaaS](https://docs.openfaas.com/) 的显著影响。因此，faas-sim 提供了两个 FunctionSimulator 实现，用于模拟 OpenFaaS 中 [Watchdog modes](https://github.com/openfaas/of-watchdog#modes) 的 forking 模式和 HTTP 模式。

相关实现位于：

```text
sim/faas/watchdogs.py
```

可以通过如下方式导入：

```python
from sim.faas import ForkingWatchdog, HTTPWatchdog
```

表示通用 Watchdog 概念的抽象类大致如下：

```python
class Watchdog(FunctionSimulator):

    def claim_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest): ...

    def release_resources(self, env: Environment, replica: FunctionReplica, request: FunctionRequest): ...

    def execute(self, env: Environment, replica: FunctionReplica, request: FunctionRequest): ...
```

`HTTPWatchdog` 使用排队机制来模拟 worker。请求在获得 token，也就是有可用 worker 之后，才会声明资源并继续执行。

`ForkingWatchdog` 不经过额外排队延迟，而是立即为每个请求声明资源并执行请求。

> 注意：使用 `ForkingWatchdog` 时，应手动限制请求数量，因为每次 fork 都会消耗内存。如果不做限制，可能会模拟出过高的并发资源消耗。

下图展示了使用 `HTTPWatchdog` 执行期间产生的日志事件，并展示了不同系统组件之间的交互关系。

![HTTPWatchdog 调用时间与组件交互](../figures/functionsim-invoke-times.png)
