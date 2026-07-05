# examples_load_balancer：faas-sim 原生负载均衡样例

本样例用于演示 faas-sim 的原生负载均衡能力，重点展示多个函数副本存在时，请求如何被路由到具体副本。

## 运行方式

将 `examples_load_balancer/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/examples_load_balancer/main.py
```

## 文件结构

```text
examples_load_balancer/
├── notebook/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── load_balancer.py
├── main.py
├── README_CN.md
├── simulator.py
└── system.py
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
examples/examples_load_balancer/outputs/
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

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 随机负载均衡；
2. 最少连接负载均衡；
3. 节点距离感知负载均衡；
4. 缓存命中优先负载均衡；
5. 请求路由与缓存状态感知调度联合分析。
