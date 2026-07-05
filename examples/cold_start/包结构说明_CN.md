# cold_start 包结构说明

`cold_start` 是 faas-sim 冷启动生命周期拆分样例包，用于演示函数副本从部署到可用、再到首次调用和热路径调用的完整过程。

## 目录结构

```text
cold_start/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── cold_start_model.py
├── main.py
├── README_CN.md
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
5. 运行三次请求；
6. 导出冷启动阶段和调用结果指标。

### `cold_start_model.py`

冷启动阶段模型文件。

该文件提供：

```text
ColdStartPhaseConfig
ColdStartModel
```

用于配置 startup、setup、first_invoke 和 warm_invoke 的确定性耗时。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
ColdStartSimulatorFactory
ColdStartFunctionSimulator
```

其核心逻辑是在 `deploy()`、`startup()`、`setup()` 和 `invoke()` 中记录 `cold_start_probe` 指标。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `cold_start_probe`、`invocations`、`replica_deployment` 等指标，并生成阶段摘要、冷启动路径摘要和 warm/cold 调用对比。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cold_start/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的冷启动生命周期拆分过程，为后续冷启动感知缓存、预热和 scale-from-zero 扩展实验提供基础。
