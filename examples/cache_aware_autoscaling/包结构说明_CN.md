# cache_aware_autoscaling 包结构说明

`cache_aware_autoscaling` 是缓存状态感知扩缩容样例包，用于演示如何组合 `R_cache` 和 `R_load` 生成目标副本数。

## 目录结构

```text
cache_aware_autoscaling/
├── inputs/
│   └── function_state_timeseries.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── autoscaler.py
├── loader.py
├── main.py
├── models.py
└── README_CN.md
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数状态时间序列；
2. 创建扩缩容配置；
3. 调用 CacheAwareAutoscaler 生成决策；
4. 生成控制计划；
5. 导出结果文件。

### `inputs/function_state_timeseries.csv`

函数状态时间序列输入文件。

字段包括：

```text
time
function_name
current_replicas
warm_replicas
n_req
request_rate
avg_response_time
avg_cold_start
cold_miss_count
memory_units
replica_capacity_rps
in_flight_requests
last_seen_age
```

### `models.py`

数据结构定义文件。

该文件定义：

```text
FunctionState
AutoscalingConfig
AutoscalingDecision
ControlPlan
```

### `loader.py`

输入读取文件。

负责从 CSV 读取函数状态时间序列。

### `autoscaler.py`

扩缩容核心逻辑文件。

该文件提供 `CacheAwareAutoscaler`，负责计算：

```text
R_cache
R_load
R_desired = max(R_cache, R_load)
```

并根据目标副本数生成动作。

### `analysis.py`

结果导出与分析文件。

该文件负责生成：

```text
cache_aware_autoscaling_decision.csv
cache_aware_autoscaling_control_plan.csv
cache_aware_autoscaling_action_summary.csv
cache_aware_autoscaling_function_summary.csv
cache_aware_autoscaling_time_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cache_aware_autoscaling/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它承接 `cache_decision` 中的 `R_cache` 思路，并进一步加入负载侧 `R_load`，为后续第四章“缓存状态与容量画像协同扩缩容”提供基础实现模板。
