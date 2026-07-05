# cache_aware_autoscaling：缓存状态感知扩缩容样例

本样例用于演示缓存状态感知扩缩容的最小实验闭环。核心思想是同时计算缓存需求副本数 `R_cache` 和负载需求副本数 `R_load`，并组合得到最终目标副本数：

```text
R_desired = max(R_cache, R_load)
```

## 运行方式

将 `cache_aware_autoscaling/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cache_aware_autoscaling/main.py
```

## 文件结构

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

## 样例目标

该样例主要回答以下问题：

1. 如何从函数状态时间序列读取负载、冷启动代价、warm 副本和当前副本数；
2. 如何计算缓存需求副本数 `R_cache`；
3. 如何计算负载需求副本数 `R_load`；
4. 如何组合得到 `R_desired = max(R_cache, R_load)`；
5. 如何根据 `R_desired` 输出 scale-out、scale-in、protect、prewarm 和 observe 动作；
6. 如何在缓存容量预算下筛选需要保护或预热的函数。

## R_cache 计算

样例先计算冷启动收益：

```text
cold_benefit = avg_cold_start * (0.6 * n_req + 1.5 * cold_miss_count + 2.0 * request_rate)
```

资源代价为：

```text
resource_cost = memory_units * resource_weight
```

缓存效用为：

```text
cache_utility = cold_benefit / resource_cost
```

当函数存在正在执行请求，或缓存效用超过阈值时，`R_cache` 至少为 1；当函数长期空闲且无请求时，`R_cache` 为 0。

## R_load 计算

负载需求副本数使用最小容量公式：

```text
R_load = ceil(request_rate / (replica_capacity_rps * target_utilization))
```

其中 `replica_capacity_rps` 表示单副本承载能力，`target_utilization` 表示目标利用率。

## R_desired 组合

最终目标副本数为：

```text
R_desired = max(R_cache, R_load)
```

这样可以避免两类错误：

```text
只看负载：低负载但高冷启动函数会被过早缩到 0
只看缓存：高负载函数可能无法及时扩容
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/cache_aware_autoscaling/outputs/
```

主要包括：

```text
cache_aware_autoscaling_decision.csv
cache_aware_autoscaling_control_plan.csv
cache_aware_autoscaling_action_summary.csv
cache_aware_autoscaling_function_summary.csv
cache_aware_autoscaling_time_summary.csv
```

## 结果解读

重点查看：

```text
cache_aware_autoscaling_decision.csv
```

其中包含：

```text
r_cache
r_load
r_desired
action
reason
capacity_status
selected_by_cache_budget
```

再查看：

```text
cache_aware_autoscaling_control_plan.csv
```

可以看到每个函数在每个时间点对应的目标副本数和控制动作。

## 后续扩展

该样例属于论文需求类功能样例。后续可以在此基础上继续扩展：

1. 将 `R_cache` 替换为论文第三章的正式缓存收益函数；
2. 将 `R_load` 接入真实请求队列长度、in-flight 请求和响应时间反馈；
3. 引入节点级容量约束和放置约束；
4. 与 `cache_aware_scheduler` 组合，形成扩缩容与节点调度协同；
5. 将 `control_plan` 接入 faas-sim 或 OpenFaaS 控制器执行器。
