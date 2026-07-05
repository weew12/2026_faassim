# trace_oracle 包结构说明

`trace_oracle` 是 faas-sim trace-driven 执行时间样例包，用于演示如何使用执行时间轨迹驱动函数调用过程。

## 目录结构

```text
trace_oracle/
├── outputs/
├── traces/
│   └── function_runtime_trace.csv
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── oracle.py
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
4. 构造两个函数部署；
5. 配置 trace-driven 模拟器；
6. 运行请求负载；
7. 导出 trace 和调用结果指标。

### `traces/function_runtime_trace.csv`

函数执行时间轨迹文件。

字段包括：

```text
function_name
sample_id
duration
```

### `oracle.py`

执行时间 Oracle 文件。

该文件提供：

```text
TraceRuntimeOracle
TraceSample
```

用于读取 CSV trace，并按照函数名称返回执行时间样本。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
TraceOracleSimulatorFactory
TraceOracleFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
sample = self.oracle.sample(function_name)
yield env.timeout(sample.duration)
```

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `trace_oracle_sample`、`invocations`、`schedule` 等指标，并生成输入 trace 摘要、实际取样摘要和调用摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/trace_oracle/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的 trace-driven 执行时间建模过程，为后续真实日志驱动仿真、冷启动建模和函数画像实验提供基础。
