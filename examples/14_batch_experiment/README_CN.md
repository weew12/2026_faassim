# batch_experiment：faas-sim 批量实验样例

本样例用于演示如何在 faas-sim 中组织多策略、多负载、多随机种子的批量仿真实验。它不关注某一个复杂策略本身，而是展示实验工程组织方式：配置生成、循环运行、单次结果导出和批量汇总。

## 运行方式

将 `batch_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/batch_experiment/main.py
```

## 文件结构

```text
batch_experiment/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── benchmark.py
├── experiment_config.py
├── main.py
├── progress.py
├── README_CN.md
├── runner.py
├── scheduler.py
└── simulator.py
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
examples/batch_experiment/outputs/
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

## 后续扩展

该样例属于通用扩展功能样例。后续可以在此基础上继续扩展：

1. 增加更多调度策略；
2. 增加不同请求到达过程；
3. 增加重复次数和置信区间；
4. 增加自动绘图脚本；
5. 接入论文实验中的缓存策略、调度策略和扩缩容策略。
