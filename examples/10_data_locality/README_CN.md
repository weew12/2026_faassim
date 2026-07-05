# data_locality：faas-sim 数据本地性样例

本样例用于演示 faas-sim / Skippy 中的数据本地性机制，重点展示 `StorageIndex`、函数数据标签、`DataLocalityPriority` 和 `simulate_data_download()` 之间的关系。

## 运行方式

将 `data_locality/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/data_locality/main.py
```

## 文件结构

```text
data_locality/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── scheduler.py
├── simulator.py
├── storage.py
└── topology.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何使用 `StorageIndex` 登记对象数据所在节点；
2. 函数如何通过标签声明需要读取哪个对象；
3. Skippy 默认 `DataLocalityPriority` 如何影响节点选择；
4. `simulate_data_download()` 如何根据数据位置触发网络传输；
5. 数据本地性感知调度和强制远端调度在下载耗时上的差异。

## 实验设计

样例构造一个小型边缘-存储拓扑：

```text
edge_near   靠近 storage_near，带宽高、延迟低
edge_mid    中等距离
edge_far    远离 storage_near，带宽低、延迟高
storage_near  保存输入对象的存储节点
```

输入对象为：

```text
video-bucket/frame-seq-001
```

函数通过以下标签声明输入数据：

```text
data.skippy.io/receives-from-storage=64M
data.skippy.io/receives-from-storage/path=video-bucket/frame-seq-001
```

样例运行两个场景：

```text
data_locality_aware   使用 Skippy 默认数据本地性优先级
forced_remote         强制调度到 edge_far，作为远端访问对比组
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/data_locality/outputs/
```

每个场景有独立子目录：

```text
outputs/data_locality_aware/
outputs/forced_remote/
```

主要结果文件包括：

```text
data_locality_scheduler_result.csv
data_locality_candidate.csv
data_locality_download.csv
flow.csv
network.csv
schedule.csv
replica_deployment.csv
data_locality_summary.csv
```

跨场景对比文件：

```text
outputs/data_locality_comparison.csv
```

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 多对象输入数据；
2. 多存储副本；
3. 数据本地性感知调度与缓存命中优先调度结合；
4. 数据下载时间对冷启动路径的影响分析；
5. 边缘节点、存储节点和函数副本的联合放置优化。
