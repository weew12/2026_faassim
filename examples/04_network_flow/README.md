# 04_network_flow：faas-sim / Ether 原生网络流样例

本样例用于演示 faas-sim 底层 Ether 网络流仿真能力，重点展示网络拓扑、路由、链路带宽、RTT、单流传输和多流共享瓶颈链路。

## 运行方式

将 `04_network_flow/` 放入项目的 `examples/` 目录后，在项目根目录运行：

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
network_flow.csv                 # 每次网络流传输的原始记录
network_route.csv                # 静态路由信息（edge client -> cloud）
network_flow_performance.csv     # 每个 flow 的完整性能指标（论文 demo 关键图）
network_flow_summary.csv          # 增强版摘要（含 throughput_mbps 和 scaling_factor）
network_bottleneck_summary.csv    # 按 bottleneck 链路分组的统计
```

### 论文 demo 关键图说明

**1. `network_flow_performance.csv`** —— 每个 flow 的完整性能

列：scenario / flow_id / bytes / size_mb / duration / start_time / finish_time / throughput_mbps / rtt_ms / hop_count / bottleneck_link / bottleneck_bandwidth_mbps / bottleneck_utilization_ratio

画图：
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("outputs/network_flow_performance.csv")
fig, ax = plt.subplots(figsize=(8, 4))
colors = df["scenario"].map({"single_flow": "steelblue", "concurrent_bottleneck": "indianred"})
ax.bar(df.flow_id, df.throughput_mbps, color=colors, label=df.scenario)
ax.set_ylabel("throughput (Mbps)")
ax.set_xlabel("flow_id")
ax.set_title("Per-flow throughput: single vs concurrent bottleneck")
plt.xticks(rotation=30, ha="right")
plt.legend()
plt.tight_layout()
plt.show()
```

**2. `network_flow_summary.csv`** —— 单流 vs 并发对比 + 延迟放大系数

`scaling_factor` 字段：concurrent 相对 single_flow 的平均延迟放大倍数。

论文叙事点：
- `scaling_factor ≈ 4.5`（74s / 16.6s）证明"3 个并发流共享 10Mbps bottleneck 时，延迟放大到原来的 4.5 倍"

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
