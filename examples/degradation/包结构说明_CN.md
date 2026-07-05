# degradation 包结构说明

`degradation` 是 faas-sim 性能退化样例包，用于演示节点并发请求导致函数执行时间变长的建模方式。

## 目录结构

```text
degradation/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── degradation_model.py
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
4. 构造多副本函数部署；
5. 使用固定节点调度器制造共节点并发；
6. 运行请求负载；
7. 导出性能退化和调用结果指标。

### `degradation_model.py`

性能退化模型文件。

该文件提供：

```text
LinearNodeContentionDegradationModel
DegradationSample
```

用于根据节点已有并发请求数计算退化后的执行时间。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
DegradationSimulatorFactory
DegradationFunctionSimulator
```

其核心逻辑是在 `invoke()` 中读取：

```text
active_requests_before = len(node.current_requests)
```

然后根据退化模型计算本次请求执行时间。

### `scheduler.py`

固定节点调度器文件。

该文件提供 `FixedNodeScheduler`，用于把多个函数副本固定部署到同一节点，从而稳定触发共节点并发退化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `degradation_probe`、`invocations`、`schedule` 等指标，并生成退化摘要和并发分布结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/degradation/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的性能退化机制，为后续节点负载感知调度、容量感知扩缩容和缓存状态感知调度提供基础。
