# network_flow：faas-sim / Ether 原生网络流样例

本样例用于演示 faas-sim 底层 Ether 网络流仿真能力，重点展示网络拓扑、路由、链路带宽、RTT、单流传输和多流共享瓶颈链路。

## 运行方式

将 `network_flow/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/network_flow/main.py
```

## 文件结构

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
examples/network_flow/outputs/
```

主要包括：

```text
network_flow.csv
network_route.csv
network_flow_summary.csv
network_bottleneck_summary.csv
```

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 镜像拉取网络样例；
2. 不同带宽和 RTT 参数敏感性实验；
3. 多流竞争同一链路的拥塞分析；
4. 网络瓶颈对函数冷启动时间的影响；
5. 云边拓扑中不同节点位置对请求响应时间的影响。
