# batch_experiment 包结构说明

`batch_experiment` 是 faas-sim 批量实验样例包，用于演示如何把单次仿真扩展为多策略、多负载、多随机种子的批量运行流程。

## 目录结构

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

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/batch_experiment/main.py
```

## 样例定位

该样例属于“通用扩展功能样例”。

它用于把前面的单个功能样例扩展为可重复、可统计、可对比的批量实验流程，为后续论文实验自动化提供基础。
