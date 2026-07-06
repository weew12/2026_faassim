# 14_batch_experiment：faas-sim 批量实验样例

本样例用于演示如何在 faas-sim 中组织多策略、多负载、多随机种子的批量仿真实验。它不关注某一个复杂策略本身，而是展示实验工程组织方式：配置生成、循环运行、单次结果导出和批量汇总。

## 运行方式

将 `14_batch_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/14_batch_experiment/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何定义策略、负载和随机种子；
2. 如何自动生成实验组合；
3. 如何为每个实验组合运行一次独立 Simulation；
4. 如何把每个 run 的原始指标保存到独立目录；
5. 如何汇总所有 run 的结果；
6. 如何生成按策略和负载聚合的摘要表。

## 默认实验组合

默认配置为：

```text
策略：
default_skippy
fixed_node

负载：
low_load      rps=3, max_requests=12
medium_load   rps=8, max_requests=24

随机种子：
1, 2
```

共计：

```text
2 × 2 × 2 = 8 次仿真
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/14_batch_experiment/outputs/
```

其中每个实验组合有独立目录：

```text
outputs/runs/<case_id>/
```

每个 run 目录包含：

```text
batch_invoke_probe.csv
case_result.csv
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

批量汇总文件位于：

```text
outputs/batch_results.csv
outputs/batch_summary.csv
```

## 进度条

样例优先使用 `tqdm` 显示总览式进度条。如果本地没有安装 `tqdm`，会自动退化为普通循环，不影响运行。

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 加载默认批量实验配置；
2. 生成实验组合；
3. 使用进度条循环运行所有 case；
4. 汇总并导出批量结果。

### `experiment_config.py`

实验配置文件。

该文件定义：

```text
PolicyConfig
WorkloadConfig
ExperimentCase
BatchExperimentConfig
```

并提供默认配置和组合生成函数。

### `runner.py`

单次实验执行器。

该文件负责根据 `ExperimentCase` 创建拓扑、Benchmark、Simulation，并根据策略切换调度器。

### `benchmark.py`

Benchmark 文件。

该文件根据负载配置部署函数并触发请求。

### `simulator.py`

函数生命周期模拟器文件。

该文件使用随机种子生成可复现的执行时间扰动，并记录 `batch_invoke_probe` 指标。

### `scheduler.py`

辅助调度器文件。

该文件提供 `FixedNodeScheduler`，用于和默认 Skippy 调度器形成策略对比。

### `analysis.py`

指标导出与汇总文件。

该文件负责导出每个 run 的原始指标、`case_result.csv`，并汇总生成：

```text
batch_results.csv
batch_summary.csv
```

### `progress.py`

进度条工具文件。

优先使用 `tqdm`，没有安装时自动 fallback。

### `outputs/`

运行输出目录。

用于保存每个 run 的结果和批量汇总结果。
