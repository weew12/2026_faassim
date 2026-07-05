# data_locality 包结构说明

`data_locality` 是 faas-sim 数据本地性样例包，用于演示 StorageIndex、Skippy DataLocalityPriority 和数据下载网络流之间的关系。

## 目录结构

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

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/data_locality/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的数据本地性机制，为后续缓存状态感知调度、数据位置感知调度和冷启动路径建模提供基础。
