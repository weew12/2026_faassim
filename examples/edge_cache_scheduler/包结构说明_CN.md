# edge_cache_scheduler 包结构说明

`edge_cache_scheduler` 是边缘缓存感知调度样例包，用于演示如何将函数 warm 实例缓存、镜像缓存、数据缓存、节点资源和边缘区域信息纳入调度评分。

## 目录结构

```text
edge_cache_scheduler/
├── inputs/
│   ├── cache_state_snapshot.csv
│   ├── function_profile.csv
│   ├── node_state_snapshot.csv
│   └── request_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── cache_index.py
├── loader.py
├── main.py
├── models.py
├── README_CN.md
├── runner.py
└── scheduler.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取节点状态；
2. 读取函数画像；
3. 读取缓存快照；
4. 读取请求 trace；
5. 运行缓存无感知和边缘缓存感知两类调度策略；
6. 导出对比结果。

### `inputs/node_state_snapshot.csv`

节点状态输入文件。

用于定义边缘节点所在区域、资源余量、当前负载、网络延迟和加速能力。

### `inputs/function_profile.csv`

函数画像输入文件。

用于定义函数冷启动代价、warm 执行时间、镜像拉取代价、数据拉取代价和资源需求。

### `inputs/cache_state_snapshot.csv`

缓存状态输入文件。

用于定义函数 warm 实例缓存、镜像缓存和数据缓存所在节点。

### `inputs/request_trace.csv`

请求 trace 输入文件。

用于驱动调度过程。

### `models.py`

数据结构定义文件。

该文件定义：

```text
NodeState
FunctionProfile
CacheEntry
RequestEvent
CandidateScore
SchedulingResult
```

### `cache_index.py`

缓存索引文件。

用于查询函数缓存、镜像缓存和数据缓存是否命中，并在请求执行后刷新缓存状态。

### `scheduler.py`

调度器文件。

该文件实现：

```text
EdgeRoundRobinScheduler
EdgeCacheAwareScheduler
```

### `runner.py`

实验执行器文件。

负责运行不同调度策略，并收集请求级调度结果和候选节点评分。

### `analysis.py`

结果导出与分析文件。

负责生成：

```text
edge_cache_scheduling_result.csv
edge_cache_candidate_score.csv
edge_cache_policy_summary.csv
edge_cache_node_summary.csv
edge_cache_function_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/edge_cache_scheduler/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它承接 `cache_aware_scheduler` 的函数缓存感知思想，进一步扩展到边缘场景下的多类缓存协同调度，为第四章“缓存状态与容量画像协同调度”提供更贴近边缘环境的实验模板。
