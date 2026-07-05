# degradation：faas-sim 性能退化样例

本样例用于演示函数执行过程中的性能退化建模。核心思想是：当同一节点上已有请求正在执行时，新到达请求会受到资源竞争影响，其执行时间被放大。

## 运行方式

将 `degradation/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/degradation/main.py
```

## 文件结构

```text
degradation/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── degradation_model.py
├── main.py
├── README_CN.md
├── scheduler.py
└── simulator.py
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
examples/degradation/outputs/
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

## 后续扩展

该样例属于 faas-sim 性能建模功能样例。后续可以在此基础上继续扩展：

1. 节点类型感知退化模型；
2. CPU / memory 利用率驱动退化模型；
3. trace-driven 退化模型；
4. 多函数共节点干扰实验；
5. 缓存状态感知调度中的共节点干扰惩罚项。
