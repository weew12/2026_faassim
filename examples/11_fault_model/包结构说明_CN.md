# fault_model 包结构说明

`fault_model` 是 faas-sim 故障模型样例包，用于演示节点故障、函数副本错误和网络退化对函数调用过程的影响。

## 目录结构

```text
fault_model/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── fault_model.py
├── main.py
├── README_CN.md
├── scheduler.py
└── simulator.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造函数部署；
5. 固定调度到目标节点；
6. 启动故障事件时间线；
7. 运行请求负载；
8. 导出故障与调用结果指标。

### `fault_model.py`

故障模型定义文件。

该文件提供：

```text
FaultEvent
FaultDecision
DeterministicFaultModel
```

用于描述故障窗口、判断请求是否受故障影响，并输出故障事件表。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
FaultModelSimulatorFactory
FaultModelFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
decision = self.fault_model.decide(env.now, request.request_id, node.name)
```

并将判定结果写入 `fault_model_probe`。

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把函数副本固定部署到目标节点，使故障窗口稳定影响请求。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `fault_model_probe`、`fault_timeline`、`invocations` 等指标，并生成故障摘要和原因分布。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/fault_model/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能扩展示例”。

它用于补齐官方 examples 中没有单独展示的故障模型过程，为后续故障感知调度、弹性恢复和节点可靠性建模实验提供基础。
