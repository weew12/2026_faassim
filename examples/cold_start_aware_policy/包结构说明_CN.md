# cold_start_aware_policy 包结构说明

`cold_start_aware_policy` 是冷启动感知函数实例保活策略样例包，用于演示如何根据冷启动代价和近期访问特征动态决定函数实例保活时间。

## 目录结构

```text
cold_start_aware_policy/
├── inputs/
│   ├── function_profile.csv
│   └── request_trace.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── loader.py
├── main.py
├── models.py
├── policies.py
├── README_CN.md
└── runner.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 读取函数画像；
2. 读取请求 trace；
3. 创建固定 keep-alive 和冷启动感知 keep-alive 策略；
4. 运行策略实验；
5. 导出对比结果。

### `inputs/function_profile.csv`

函数画像输入文件。

用于定义函数冷启动耗时、热路径耗时和缓存容量占用。

### `inputs/request_trace.csv`

请求 trace 输入文件。

用于驱动函数 warm / cold 状态变化。

### `models.py`

数据结构定义文件。

该文件定义：

```text
FunctionProfile
RequestEvent
WarmEntry
RequestResult
PolicyDecision
EvictionEvent
```

### `loader.py`

输入读取文件。

负责读取函数画像和请求 trace。

### `policies.py`

策略实现文件。

该文件实现：

```text
FixedKeepAlivePolicy
ColdStartAwarePolicy
```

### `runner.py`

实验执行器文件。

负责将请求 trace 输入到不同策略，并收集请求结果、策略决策和驱逐事件。

### `analysis.py`

结果导出与分析文件。

负责生成：

```text
cold_start_request_result.csv
cold_start_policy_decision.csv
cold_start_eviction.csv
cold_start_policy_summary.csv
cold_start_function_summary.csv
cold_start_decision_summary.csv
```

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/cold_start_aware_policy/main.py
```

## 样例定位

该样例属于“论文需求类功能样例”。

它在 `cache_policy` 的基础上进一步强调冷启动感知保活时间决策，为第三章函数实例缓存策略和后续 `cache_decision` 提供策略层实现模板。
