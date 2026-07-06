# 02_load_balancer：faas-sim 原生负载均衡样例

本样例用于演示 faas-sim 的原生负载均衡能力，重点展示多个函数副本存在时，请求如何被路由到具体副本。

## 运行方式

将 `02_load_balancer/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/02_load_balancer/main.py
```

## 样例目标

该样例主要回答以下问题：

1. faas-sim 中负载均衡器在什么情况下被调用；
2. 多个 RUNNING 副本存在时，请求如何选择目标副本；
3. 如何替换 `DefaultFaasSystem.load_balancer`；
4. 如何记录每次请求路由决策；
5. 如何导出 `load_balancer.csv`；
6. 如何统计请求在副本之间的分布。

## 输出文件

运行结束后，结果会保存到：

```text
examples/02_load_balancer/outputs/
```

主要包括：

```text
load_balancer.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
load_balancer_summary.csv
load_balancer_replica_distribution.csv
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 注册函数镜像；
3. 构造拥有 3 个副本的 `FunctionDeployment`；
4. 创建 `Simulation`；
5. 启用可观测轮询负载均衡器；
6. 触发请求负载；
7. 导出负载均衡结果指标。

### `load_balancer.py`

负载均衡策略文件。

该文件提供：

```text
InstrumentedRoundRobinLoadBalancer
```

它保持轮询负载均衡语义，同时把每次请求路由决策写入 `load_balancer` 指标。

### `system.py`

FaaS 系统创建文件。

该文件提供 `create_load_balancer_faas_system(env)`，用于创建 `DefaultFaasSystem` 并替换其 `load_balancer` 字段。

### `simulator.py`

函数执行模拟器文件。

该文件提供稳定函数执行时间，便于观察请求路由分布，而不是把实验差异混入执行模型。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `load_balancer`、`invocations`、`schedule` 等 DataFrame，并生成路由摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
