# cold_start_aware_policy：冷启动感知函数实例保活策略样例

本样例用于演示冷启动感知函数实例保活策略。它将函数 warm 实例抽象为有限容量缓存，并比较固定 keep-alive 策略与冷启动感知 keep-alive 策略的差异。

## 运行方式

将 `cold_start_aware_policy/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cold_start_aware_policy/main.py
```

## 文件结构

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

## 样例目标

该样例主要回答以下问题：

1. 如何把函数 warm 实例保活抽象为有限容量缓存；
2. 如何根据请求 trace 判断 warm hit 和 cold miss；
3. 如何比较固定 keep-alive 和冷启动感知 keep-alive；
4. 如何根据冷启动代价、近期访问频率和资源占用计算保活效用；
5. 如何在容量预算下执行保活、延长、过期和驱逐决策。

## 策略说明

样例包含两类策略：

```text
fixed_keep_alive      固定保活窗口，所有函数请求后保活 2 个时间单位
cold_start_aware      根据冷启动代价、近期访问频率和资源占用动态计算保活窗口
```

冷启动感知策略的最小效用公式为：

```text
utility = cold_start_duration * (1 + recent_rate) / memory_units
```

动态保活窗口为：

```text
keep_alive_window = base_window + 1.2 * cold_start_duration + 2.0 * recent_rate - 0.3 * memory_units
```

该公式用于演示机制，后续可以替换为论文第三章中的缓存收益函数或在线效用模型。

## 输入文件

函数画像位于：

```text
inputs/function_profile.csv
```

字段包括：

```text
function_name
cold_start_duration
warm_duration
memory_units
```

请求 trace 位于：

```text
inputs/request_trace.csv
```

字段包括：

```text
time
function_name
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/cold_start_aware_policy/outputs/
```

主要包括：

```text
cold_start_request_result.csv
cold_start_policy_decision.csv
cold_start_eviction.csv
cold_start_policy_summary.csv
cold_start_function_summary.csv
cold_start_decision_summary.csv
```

## 结果解读

重点查看：

```text
cold_start_policy_summary.csv
```

其中包含：

```text
hit_rate
avg_latency
total_cold_start_penalty
avg_keep_alive_window
avg_cache_used
eviction_count
```

再查看：

```text
cold_start_policy_decision.csv
```

可以分析每次请求后策略如何决定延长保活窗口，以及不同函数对应的保活效用。

## 后续扩展

该样例属于论文需求类功能样例。后续可以在此基础上继续扩展：

1. 将保活效用替换为论文中的 `R_cache`；
2. 引入节点异构冷启动时间；
3. 引入 OpenFaaS scale-to-zero 与 prewarm 动作；
4. 将策略输出接入 `cache_decision`；
5. 与 `cache_aware_autoscaling` 组合，形成保活策略与扩缩容决策闭环。
