# cache_policy 包结构说明

`cache_policy` 是函数实例缓存策略样例包，用于演示如何把函数 warm 实例管理抽象为缓存策略问题。

## 目录结构

```text
cache_policy/
├── inputs/
│   └── request_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── cache_model.py
├── function_catalog.py
├── main.py
├── policies.py
├── README_CN.md
├── runner.py
└── workload.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取请求 trace；
2. 加载函数规格表；
3. 创建缓存策略；
4. 运行缓存策略实验；
5. 导出策略对比结果。

### `inputs/request_trace.csv`

请求 trace 文件。

字段包括：

```text
time
function_name
```

### `function_catalog.py`

函数规格表文件。

该文件定义函数冷启动耗时、热路径耗时和缓存资源占用。

### `cache_model.py`

缓存状态模型文件。

该文件定义：

```text
CacheEntry
FunctionCache
RequestResult
EvictionEvent
CacheStateRecord
```

### `policies.py`

缓存策略文件。

该文件实现：

```text
FIFO
LRU
UtilityAware
```

### `runner.py`

实验执行器文件。

该文件负责把请求 trace 送入每个策略，记录请求级结果、驱逐事件和缓存状态。

### `analysis.py`

结果导出与分析文件。

该文件负责生成：

```text
cache_request_result.csv
cache_eviction.csv
cache_state.csv
cache_policy_summary.csv
cache_function_summary.csv
cache_eviction_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cache_policy/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它用于把冷启动感知函数实例缓存的核心逻辑独立抽象出来，为后续 `cache_decision`、`cache_aware_scheduler` 和 `cache_aware_autoscaling` 样例提供基础。
