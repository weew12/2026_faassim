# resource_monitor 包结构说明

`resource_monitor` 是 faas-sim 原生资源监控样例包，用于演示 ResourceState 与 ResourceMonitor 的基本使用方式。

## 目录结构

```text
resource_monitor/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
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
5. 运行请求负载；
6. 导出资源监控和调用结果指标。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
ResourceMonitorSimulatorFactory
ResourceMonitorFunctionSimulator
```

其核心逻辑是在 `invoke()` 中调用：

```text
env.resource_state.put_resource(...)
env.resource_state.remove_resource(...)
```

从而让 ResourceMonitor 能够采集到资源使用变化。

### `analysis.py`

指标导出与分析文件。

该文件负责导出资源监控、调用、调度和部署生命周期相关指标，并生成摘要结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/resource_monitor/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的 ResourceState / ResourceMonitor 机制，为后续资源感知调度、容量感知扩缩容和缓存替换实验提供基础。
