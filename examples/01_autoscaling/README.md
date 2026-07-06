# 01_autoscaling：faas-sim 原生自动伸缩样例

本样例用于演示 faas-sim 的原生自动伸缩能力，重点展示函数部署、请求负载生成、自动伸缩触发、伸缩指标导出和副本数量时间线分析。

## 运行方式

将 `examples_autoscaling/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/01_autoscaling/main.py
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
examples/01_autoscaling/outputs/
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

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 注册函数镜像；
3. 构造 `FunctionDeployment`；
4. 设置 `ScalingConfiguration`；
5. 创建 `Simulation`；
6. 启用自动伸缩 FaaS 系统；
7. 运行请求负载；
8. 导出结果指标。

### `system.py`

FaaS 系统创建文件。

该文件提供 `create_autoscaling_faas_system(env)`，用于创建：

```python
DefaultFaasSystem(env, scale_by_average_requests=True)
```

这样 faas-sim 就会启用基于平均请求负载的原生自动伸缩逻辑。

### `simulator.py`

函数执行模拟器文件。

该文件提供：

```text
AutoscalingSimulatorFactory
AutoscalingFunctionSimulator
```

用于模拟函数副本的部署、启动、调用和关闭过程。

### `analysis.py`

指标导出与分析文件。

该文件负责从 `sim.env.metrics` 中提取常用 DataFrame，并保存到 `outputs/` 目录。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
