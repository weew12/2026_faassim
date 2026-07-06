# 04_network_flow：faas-sim / Ether 原生网络流样例

本样例用于演示 faas-sim 底层 Ether 网络流仿真能力，重点展示网络拓扑、路由、链路带宽、RTT、单流传输和多流共享瓶颈链路。

## 运行方式

将 `network_flow/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/04_network_flow/main.py
```

## 样例目标

该样例主要回答以下问题：

1. Ether 中如何创建网络节点和链路；
2. 为什么不能直接连接两个计算节点，而需要经过 Link 或透明节点；
3. 如何查询两个节点之间的 Route；
4. Flow 如何根据路由中的链路带宽推进仿真时间；
5. 多个 Flow 共享瓶颈链路时，传输时间如何变化；
6. 如何将网络流结果导出为 CSV。

## 输出文件

运行结束后，结果会保存到：

```text
examples/04_network_flow/outputs/
```

主要包括：

```text
network_flow.csv
network_route.csv
network_flow_summary.csv
network_bottleneck_summary.csv
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
