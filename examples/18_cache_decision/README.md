# cache_decision：冷启动感知缓存决策样例

本样例用于演示函数实例缓存决策过程。它基于函数画像快照计算冷启动收益、资源代价和缓存效用，并输出 keep warm、prewarm、eviction 和 observe 等决策结果。

## 运行方式

将 `cache_decision/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cache_decision/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何从函数画像快照中读取请求量、冷启动代价、资源占用和副本状态；
2. 如何计算冷启动收益、资源代价和缓存效用；
3. 如何生成 `keep_warm`、`prewarm_candidate`、`eviction_candidate` 和 `observe` 四类决策；
4. 如何在容量预算下选择需要保护或预热的函数；
5. 如何把缓存决策转换为控制建议。

## 决策类型

样例输出四类核心决策：

```text
keep_warm            当前已有 warm 副本，且冷启动收益较高，应继续保护
prewarm_candidate    当前没有副本，但冷启动收益较高，可作为预热候选
eviction_candidate   当前有副本，但长期空闲或效用较低，可作为释放候选
observe              暂不动作，仅观察
```

## 最小效用公式

样例使用如下最小公式计算冷启动收益：

```text
cold_benefit = avg_cold_start * (0.6 * n_req + 1.4 * cold_miss_count + 2.0 * request_rate)
```

资源代价为：

```text
resource_cost = memory_units * resource_weight
```

缓存效用为：

```text
utility_score = cold_benefit / resource_cost
```

这些公式用于样例演示，后续可以替换为论文中的 `R_cache`、在线画像状态或更完整的效用模型。

## 输出文件

运行结束后，结果会保存到：

```text
examples/cache_decision/outputs/
```

主要包括：

```text
cache_decision_detail.csv
cache_decision_summary.csv
cache_decision_rank.csv
cache_eviction_candidate.csv
cache_control_hint.csv
```

## 结果解读

重点查看：

```text
cache_decision_detail.csv
```

其中包含每个函数的：

```text
cold_benefit
resource_cost
utility_score
decision
reason
capacity_status
selected_by_budget
```

再查看：

```text
cache_control_hint.csv
```

可以看到每类决策对应的控制建议，例如保护当前副本、预热到 1 个副本、作为 scale-to-zero 候选或继续观察。

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
