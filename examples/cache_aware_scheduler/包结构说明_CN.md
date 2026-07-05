# cache_aware_scheduler 包结构说明

`cache_aware_scheduler` 是缓存状态感知调度样例包，用于演示调度器如何利用函数 warm 实例缓存状态选择目标节点。

## 目录结构

```text
cache_aware_scheduler/
├── inputs/
│   ├── cache_state_snapshot.csv
│   └── workload.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── benchmark.py
├── cache_state.py
├── main.py
├── README_CN.md
├── scheduler.py
├── simulator.py
└── workload.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取缓存状态快照；
2. 读取请求负载；
3. 运行缓存无感知调度场景；
4. 运行缓存状态感知调度场景；
5. 导出跨场景对比结果。

### `inputs/cache_state_snapshot.csv`

节点级函数 warm 缓存快照。

用于描述哪些函数在某些节点上已有 warm 实例。

### `inputs/workload.csv`

请求负载文件。

用于描述不同函数请求的到达顺序。

### `cache_state.py`

缓存状态索引文件。

该文件提供 `CacheStateIndex`，用于按函数和节点查询缓存命中状态。

### `scheduler.py`

调度器文件。

该文件提供：

```text
CacheAwareScheduler
CacheBlindScheduler
```

前者根据缓存状态计算候选节点得分，后者不读取缓存状态，作为稳定对比基线。

### `benchmark.py`

Benchmark 文件。

该文件负责部署 workload 中出现的函数，并按请求序列触发调用。

### `simulator.py`

函数生命周期模拟器文件。

该文件在 invoke 阶段根据调度节点是否存在目标函数 warm 缓存，记录 cache hit / miss 和冷启动惩罚。

### `analysis.py`

结果导出与分析文件。

该文件负责导出候选节点评分、调度结果、请求级结果和跨场景对比摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cache_aware_scheduler/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它承接 `cache_decision` 的缓存状态信息，进一步展示缓存状态如何进入调度评分，为后续缓存感知扩缩容和协同调度实验提供基础。


## 修复说明

本样例中每个函数使用独立镜像名，避免 faas-sim 按 image 统计副本数量时，把多个函数合并到同一 `scale_max` 约束下，导致后续函数副本不被创建。


## FunctionRequest 兼容性修复

当前 faas-sim 版本中的 `FunctionRequest.__init__()` 不支持 `request_id` 关键字参数。本样例在 `benchmark.py` 中按原生方式创建请求对象后，再写入 workload 中的请求编号。


## DefaultFaasSystem.invoke 兼容性修复

当前 faas-sim 版本中的 `DefaultFaasSystem.invoke()` 只接收 `FunctionRequest`，不接收 `FunctionDeployment`。本样例已按该接口修正调用方式。
