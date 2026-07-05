# skippy_scheduler：faas-sim 原生 Skippy 默认调度机制样例

本样例用于演示 faas-sim 中默认 Skippy 调度机制，重点展示资源过滤、节点可行性判断、节点选择和 `SchedulingResult` 的含义。

## 运行方式

将 `skippy_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/skippy_scheduler/main.py
```

## 文件结构

```text
skippy_scheduler/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── scheduler.py
└── simulator.py
```

## 样例目标

该样例主要回答以下问题：

1. Skippy 默认调度器如何参与 faas-sim 函数副本部署；
2. 资源过滤如何影响候选节点数量；
3. `SchedulingResult.suggested_host` 表示什么；
4. `SchedulingResult.feasible_nodes` 表示什么；
5. `SchedulingResult.needed_images` 表示什么；
6. 如何导出调度过程指标。

## 输出文件

运行结束后，结果会保存到：

```text
examples/skippy_scheduler/outputs/
```

主要包括：

```text
skippy_scheduler_result.csv
skippy_scheduler_candidate.csv
schedule.csv
allocation.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv
flow.csv
skippy_scheduler_summary.csv
skippy_selected_node_distribution.csv
```

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 增加自定义谓词；
2. 增加自定义优先级函数；
3. 对比默认 Skippy 调度器与随机调度器；
4. 引入镜像本地性与数据本地性分析；
5. 为缓存状态感知调度器提供 baseline。
