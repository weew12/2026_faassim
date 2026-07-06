# data_locality：faas-sim 数据本地性样例

本样例用于演示 faas-sim / Skippy 中的数据本地性机制，重点展示 `StorageIndex`、函数数据标签、`DataLocalityPriority` 和 `simulate_data_download()` 之间的关系。

## 运行方式

将 `data_locality/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/data_locality/main.py
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

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建数据本地性拓扑；
2. 创建 StorageIndex；
3. 注册函数镜像；
4. 构造带数据标签的函数部署；
5. 分别运行数据本地性感知调度和强制远端调度；
6. 导出结果并生成对比摘要。

### `topology.py`

拓扑构建文件。

该文件创建 `edge_near`、`edge_mid`、`edge_far` 和 `storage_near`，并设置不同带宽和延迟，用于稳定制造近数据节点与远数据节点的差异。

### `storage.py`

对象存储索引文件。

该文件提供：

```text
DEFAULT_DATA_OBJECT
build_storage_index()
```

用于登记 `video-bucket/frame-seq-001` 位于 `storage_near`。

### `scheduler.py`

调度器文件。

该文件提供：

```text
InstrumentedDataLocalityScheduler
ForcedNodeScheduler
```

前者保留 Skippy 默认调度语义并记录候选节点数据本地性信息，后者用于构造强制远端对比组。

### `simulator.py`

函数生命周期模拟器文件。

该文件提供：

```text
DataLocalitySimulatorFactory
DataLocalityFunctionSimulator
```

其核心逻辑是在 `setup()` 阶段调用：

```text
simulate_data_download(env, replica)
```

从而根据数据路径和 StorageIndex 触发数据下载。

### `analysis.py`

指标导出与分析文件。

该文件负责导出调度、下载、网络流、部署和调用指标，并生成场景摘要和跨场景对比。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
