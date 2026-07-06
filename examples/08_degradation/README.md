# 08_degradation：faas-sim 性能退化样例

本样例用于演示函数执行过程中的性能退化建模。核心思想是：当同一节点上已有请求正在执行时，新到达请求会受到资源竞争影响，其执行时间被放大。

## 运行方式

将 `degradation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/08_degradation/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何利用 `node.current_requests` 观察节点当前并发负载；
2. 多个请求共节点执行时如何构造性能退化；
3. 如何将基础执行时间放大为退化后的执行时间；
4. 如何记录每次请求的退化因子；
5. 如何导出并发请求数与执行时间之间的关系。

## 退化模型

样例使用线性节点竞争退化模型：

```text
final_duration = base_duration * (1 + alpha * active_requests_before)
```

其中：

```text
base_duration：无竞争时的基础执行时间
active_requests_before：当前请求加入前节点上已有的并发请求数
alpha：每个并发请求带来的执行时间放大系数
final_duration：退化后的本次请求执行时间
```

## 实验设计

样例部署一个函数：

```text
degradation-python-pi
```

配置如下：

```text
scale_min = 3
scale_max = 3
```

同时使用 `FixedNodeScheduler` 将副本固定调度到同一节点，并通过较高请求速率制造请求重叠，从而稳定产生性能退化现象。

## 输出文件

运行结束后，结果会保存到：

```text
examples/08_degradation/outputs/
```

主要包括：

```text
degradation_probe.csv
degradation_summary.csv
degradation_concurrency_distribution.csv
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
resource.csv
resources.csv
resource_monitor.csv
resource_state.csv
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造多副本函数部署；
5. 使用固定节点调度器制造共节点并发；
6. 运行请求负载；
7. 导出性能退化和调用结果指标。

### `degradation_model.py`

性能退化模型文件。

该文件提供：

```text
LinearNodeContentionDegradationModel
DegradationSample
```

用于根据节点已有并发请求数计算退化后的执行时间。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
DegradationSimulatorFactory
DegradationFunctionSimulator
```

其核心逻辑是在 `invoke()` 中读取：

```text
active_requests_before = len(node.current_requests)
```

然后根据退化模型计算本次请求执行时间。

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把多个函数副本固定部署到同一节点，从而稳定触发共节点并发退化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `degradation_probe`、`invocations`、`schedule` 等指标，并生成退化摘要和并发分布结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
