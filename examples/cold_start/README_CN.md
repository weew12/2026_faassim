# cold_start：faas-sim 冷启动生命周期拆分样例

本样例用于演示 faas-sim 中函数副本冷启动路径的拆分建模方法，重点展示 `deploy`、`startup`、`setup`、`first_invoke` 和 `warm_invoke` 的区别。

## 运行方式

将 `cold_start/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cold_start/main.py
```

## 文件结构

```text
cold_start/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── cold_start_model.py
├── main.py
├── README_CN.md
└── simulator.py
```

## 样例目标

该样例主要回答以下问题：

1. faas-sim 中函数副本启动过程如何经过 deploy、startup 和 setup；
2. `docker.pull()` 如何作为 deploy 阶段的一部分影响冷启动路径；
3. 如何区分首次请求 `first_invoke` 和热路径请求 `warm_invoke`；
4. 如何记录每个阶段的开始时间、结束时间和阶段耗时；
5. 如何生成副本级冷启动路径摘要。

## 阶段定义

样例将函数启动和调用过程拆成五类事件：

```text
deploy        镜像拉取或部署准备阶段
startup       容器/运行时启动阶段
setup         函数业务初始化阶段
first_invoke  副本首次请求执行阶段
warm_invoke   副本后续热路径请求执行阶段
```

其中冷启动激活路径定义为：

```text
cold_activation_duration = deploy + startup + setup
```

首次请求路径定义为：

```text
first_request_path_duration = deploy + startup + setup + first_invoke
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/cold_start/outputs/
```

主要包括：

```text
cold_start_probe.csv
cold_start_phase_summary.csv
cold_start_replica_path_summary.csv
cold_start_warm_cold_compare.csv
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

## 重要说明

faas-sim 默认流程是在函数部署阶段创建并启动副本，请求到达时通常已经存在 RUNNING 副本。因此本样例重点刻画“副本从创建到可用”的冷启动路径，而不是 OpenFaaS 网关 scale-from-zero 场景下的请求阻塞等待过程。

后续如果要研究 scale-from-zero，可以在此基础上增加自定义 FaaSSystem 或控制器逻辑，使请求到达时触发副本创建并统计请求等待时间。

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 不同镜像大小对 deploy 阶段的影响；
2. 不同节点类型对 startup / setup 的影响；
3. trace-driven 冷启动阶段耗时；
4. scale-from-zero 请求等待建模；
5. 冷启动感知函数实例缓存与预热策略实验。
