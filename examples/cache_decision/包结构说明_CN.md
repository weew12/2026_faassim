# cache_decision 包结构说明

`cache_decision` 是冷启动感知函数实例缓存决策样例包，用于演示如何从函数画像快照生成缓存决策和控制建议。

## 目录结构

```text
cache_decision/
├── inputs/
│   └── function_profile_snapshot.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── advisor.py
├── analysis.py
├── decision_model.py
├── main.py
├── profiles.py
└── README_CN.md
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数画像快照；
2. 创建缓存决策配置；
3. 调用 Advisor 生成缓存决策；
4. 生成控制建议；
5. 导出结果文件。

### `inputs/function_profile_snapshot.csv`

函数画像快照输入文件。

字段包括：

```text
function_name
current_replicas
warm_replicas
n_req
cold_miss_count
avg_cold_start
warm_duration
memory_units
last_seen_age
in_flight_requests
request_rate
```

### `profiles.py`

画像读取文件。

该文件定义 `FunctionProfile`，并提供 CSV 读取函数。

### `decision_model.py`

决策数据结构文件。

该文件定义：

```text
CacheDecisionConfig
CacheDecision
ControlHint
```

### `advisor.py`

缓存决策核心文件。

该文件提供 `CacheDecisionAdvisor`，负责计算效用、分类决策、容量预算选择和控制建议。

### `analysis.py`

结果导出与分析文件。

该文件负责生成：

```text
cache_decision_detail.csv
cache_decision_summary.csv
cache_decision_rank.csv
cache_eviction_candidate.csv
cache_control_hint.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cache_decision/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它承接 `cache_policy` 中的缓存问题抽象，进一步转向在线系统中的缓存决策输出，为后续 `cache_aware_scheduler` 和 `cache_aware_autoscaling` 提供决策输入。
