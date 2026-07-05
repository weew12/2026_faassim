# network_flow 包结构说明

`network_flow` 是 faas-sim / Ether 原生网络流样例包，用于演示网络拓扑、路由和 Flow 传输耗时。

## 目录结构

```text
network_flow/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── flow_runner.py
├── main.py
├── README_CN.md
└── topology.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 构建网络拓扑；
2. 收集路由信息；
3. 运行单流场景；
4. 运行并发瓶颈链路场景；
5. 导出结果指标。

### `topology.py`

网络拓扑构建文件。

该文件构造一个边缘到云端的共享瓶颈拓扑，用于观察多个 Flow 竞争同一链路时的网络行为。

### `flow_runner.py`

网络流执行文件。

该文件直接使用 `ether.core.Flow` 启动网络传输，并记录每个 Flow 的开始时间、结束时间、持续时间、传输字节数、路径和瓶颈链路。

### `analysis.py`

结果导出与摘要分析文件。

该文件负责保存：

```text
network_flow.csv
network_route.csv
network_flow_summary.csv
network_bottleneck_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/network_flow/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的 Ether 网络流机制，为后续镜像拉取、冷启动网络耗时和边缘网络瓶颈实验提供基础。
