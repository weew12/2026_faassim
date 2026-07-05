# cache_policy：函数实例缓存策略样例

本样例用于演示函数实例缓存策略的最小实验闭环。它将函数副本是否保持 warm 抽象为缓存状态，并根据请求 trace、冷启动代价和资源占用比较不同缓存策略的效果。

## 运行方式

将 `cache_policy/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cache_policy/main.py
```

## 文件结构

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

## 样例目标

该样例主要回答以下问题：

1. 如何把函数实例保持 warm 抽象为缓存问题；
2. 如何根据请求 trace 判断 warm hit 和 cold miss；
3. 如何建模函数冷启动代价和缓存资源占用；
4. 如何实现 FIFO、LRU 和 Utility-aware 三类缓存策略；
5. 如何记录请求级延迟、冷启动惩罚、驱逐事件和缓存状态；
6. 如何生成策略级命中率和延迟对比结果。

## 默认策略

样例包含三类策略：

```text
fifo            先进先出，驱逐最早进入缓存的函数
lru             最近最少使用，驱逐最长时间未访问的函数
utility_aware   冷启动收益感知，驱逐单位资源效用最低的函数
```

`utility_aware` 使用的最小效用公式为：

```text
utility = cold_start_duration * (1 + access_count) / memory_units
```

该公式只作为样例中的最小可运行版本，后续可以替换为论文中的 `R_cache` 或更完整的在线效用模型。

## 输入文件

请求 trace 位于：

```text
inputs/request_trace.csv
```

字段为：

```text
time,function_name
```

函数规格在 `function_catalog.py` 中定义，包括：

```text
cold_start_duration
warm_duration
memory_units
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/cache_policy/outputs/
```

主要包括：

```text
cache_request_result.csv
cache_eviction.csv
cache_state.csv
cache_policy_summary.csv
cache_function_summary.csv
cache_eviction_summary.csv
```

## 结果解读

重点查看：

```text
cache_policy_summary.csv
```

其中：

```text
hit_rate                    缓存命中率
avg_latency                 平均请求延迟
total_cold_start_penalty    总冷启动惩罚
avg_cache_used_after        平均缓存资源占用
```

再结合：

```text
cache_eviction.csv
```

可以分析不同策略在容量受限条件下驱逐了哪些函数，以及驱逐原因。

## 后续扩展

该样例属于论文需求类功能样例。后续可以在此基础上继续扩展：

1. 将 Utility-aware 策略替换为论文中的 `R_cache`；
2. 引入节点级异构冷启动时间；
3. 引入函数实例过期时间和 keep-alive 时间；
4. 联合镜像缓存与函数实例缓存；
5. 接入 faas-sim 的调度与扩缩容流程，形成缓存状态感知调度实验。
