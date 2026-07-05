# cosimulation 包结构说明

`cosimulation` 是 faas-sim 协同仿真样例包，用于演示 faas-sim 如何与外部控制器或外部环境模型进行状态交换。

## 目录结构

```text
cosimulation/
├── inputs/
│   └── external_environment_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── context.py
├── controller.py
├── external_model.py
├── main.py
├── README_CN.md
└── simulator.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取外部环境 trace；
2. 创建共享协同仿真上下文；
3. 创建外部控制器；
4. 创建 faas-sim Simulation；
5. 启动请求负载和控制循环；
6. 导出协同仿真结果。

### `inputs/external_environment_trace.csv`

外部环境 trace 文件。

用于描述不同时段的请求速率、函数运行时间放大系数、额外网络延迟和控制动作。

### `context.py`

共享上下文文件。

该文件提供：

```text
ExternalPhase
CosimulationContext
```

用于在外部控制器和函数模拟器之间共享外部状态。

### `external_model.py`

外部模型文件。

该文件提供 `ExternalEnvironmentTrace`，负责读取 CSV trace 并按仿真时间查询当前外部阶段。

### `controller.py`

外部控制器文件。

该文件提供 `ExternalController`，按照固定控制周期更新共享上下文，并记录 `cosim_exchange` 和 `cosim_phase` 指标。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
CosimulationSimulatorFactory
CosimulationFunctionSimulator
```

其核心逻辑是在 `invoke()` 阶段读取共享上下文，并根据外部状态计算函数执行时间。

### `analysis.py`

指标导出与分析文件。

该文件负责导出协同仿真指标，并生成阶段级调用摘要和控制交换摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cosimulation/main.py
```

## 样例定位

该样例属于“通用扩展功能样例”。

它用于把 faas-sim 从单一离散事件仿真扩展为可与外部模型交互的协同仿真框架，为后续接入外部调度器、在线学习控制器、网络仿真器和真实 trace 提供基础。
