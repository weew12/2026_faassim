# cache_aware_scheduler：缓存状态感知调度样例

本样例用于演示缓存状态感知调度的最小实验闭环。调度器读取节点级函数 warm 实例缓存状态，在候选节点中优先选择已有目标函数缓存的节点，从而降低冷启动惩罚。

## 运行方式

将 `cache_aware_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/19_cache_aware_scheduler/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何读取节点级函数 warm 实例缓存快照；
2. 如何在调度阶段识别目标函数是否已有缓存节点；
3. 如何对候选节点计算 cache-aware score；
4. 如何与缓存无感知调度进行对比；
5. 如何导出候选节点评分、最终调度结果和请求级缓存命中情况。

## 输入文件

缓存快照位于：

```text
inputs/cache_state_snapshot.csv
```

字段包括：

```text
function_name
node_name
warm_replicas
cached
last_access_age
avg_cold_start
memory_units
```

请求负载位于：

```text
inputs/workload.csv
```

字段包括：

```text
request_id
function_name
arrival_time
```

## 调度评分

样例使用最小 cache-aware 打分：

```text
total_score = cache_hit_score + freshness_score + load_score
```

其中：

```text
cache_hit_score     目标节点已有该函数 warm 缓存时获得高分
freshness_score     缓存越新分数越高
load_score          节点已放置 Pod 越少分数越高
```

该公式用于展示机制，后续可以替换为论文第四章中的缓存状态与容量画像协同调度评分。

## 输出文件

运行结束后，结果会保存到：

```text
examples/19_cache_aware_scheduler/outputs/
```

主要包括：

```text
cache_state_snapshot.csv
cache_blind/cache_aware_scheduler_summary.csv
cache_blind/cache_aware_request_probe.csv
cache_blind/cache_aware_scheduler_result.csv
cache_aware/cache_aware_candidate.csv
cache_aware/cache_aware_scheduler_result.csv
cache_aware/cache_aware_request_probe.csv
cache_aware/cache_aware_scheduler_summary.csv
cache_aware_scheduler_comparison.csv
```

## 结果解读

重点查看：

```text
cache_aware/cache_aware_candidate.csv
```

该文件记录每个候选节点的缓存命中状态和调度得分。

```text
cache_aware_scheduler_comparison.csv
```

该文件对比 `cache_blind` 和 `cache_aware` 两个场景的缓存命中率、平均请求耗时和总冷启动惩罚。

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
