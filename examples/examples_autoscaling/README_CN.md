# examples_autoscaling：faas-sim 原生自动伸缩样例

本样例用于演示 faas-sim 的原生自动伸缩能力，重点展示函数部署、请求负载生成、自动伸缩触发、伸缩指标导出和副本数量时间线分析。

## 运行方式

将 `examples_autoscaling/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/examples_autoscaling/main.py
```

## 文件结构

```text
examples_autoscaling/
├── notebook/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── simulator.py
└── system.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何在 faas-sim 中配置函数自动伸缩；
2. 如何使用 `ScalingConfiguration` 设置最小副本数、最大副本数和目标负载；
3. 如何启用 `DefaultFaasSystem(scale_by_average_requests=True)`；
4. 如何用请求生成器产生持续负载；
5. 如何导出 `scale`、`schedule`、`replica_deployment` 和 `invocations` 指标；
6. 如何将自动伸缩结果保存为 CSV 文件。

## 输出文件

运行结束后，结果会保存到：

```text
examples/examples_autoscaling/outputs/
```

主要包括：

```text
scale.csv
schedule.csv
function_deployment.csv
replica_deployment.csv
invocations.csv
flow.csv
autoscaling_replica_timeline.csv
autoscaling_summary.csv
```

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 缓存状态感知扩缩容；
2. `R_cache` 与 `R_load` 联合决策；
3. 不同负载强度下的副本变化对比；
4. 不同自动伸缩策略的批量实验；
5. 与缓存状态感知调度器联合验证。
