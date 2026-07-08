# examples/analysis

本示例演示如何运行一次 faas-sim 仿真，并从 `env.metrics` 中提取结果表做后处理分析。

## 运行方式

在项目根目录执行：

```bash
python -u examples/analysis/main.py
```

## 示例目标

- 复用 `examples.basic` 的拓扑和 benchmark。
- 复用 `examples.custom_function_sim` 的自定义函数模拟器。
- 从 metrics 中提取部署、调度、调用、网络和资源相关 DataFrame。
- 计算 `invocations.t_exec` 的平均执行时间，作为最小分析示例。

## 文件说明

- `main.py`：运行仿真、提取指标表并输出平均执行时间。
- `examples_analysis_中文注释版.ipynb`：交互式分析版 notebook，适合逐步查看各个指标表。
- `__init__.py`：包说明。

## 关键指标表

`main.py` 会提取以下表：

- `allocation`
- `invocations`
- `scale`
- `schedule`
- `replica_deployment`
- `function_deployments`
- `function_deployment`
- `function_deployment_lifecycle`
- `functions`
- `flow`
- `network`
- `node_utilization`
- `function_utilization`
- `fets`

这些表来自 `sim.env.metrics.extract_dataframe(name)`，可以继续用于 CSV 导出、统计分析或绘图。
