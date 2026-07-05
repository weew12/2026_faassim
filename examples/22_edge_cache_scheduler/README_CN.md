# edge_cache_scheduler：边缘缓存感知调度样例

本样例用于演示边缘缓存感知调度。与只考虑资源或轮转的调度方式不同，边缘缓存感知调度同时考虑函数 warm 实例缓存、镜像缓存、数据缓存、边缘区域亲和性和节点负载。

## 运行方式

将 `edge_cache_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/edge_cache_scheduler/main.py
```

## 文件结构

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

## 样例目标

该样例主要回答以下问题：

1. 如何把边缘节点状态、函数画像、缓存状态和请求 trace 组织为调度输入；
2. 如何区分函数 warm 实例缓存、镜像缓存和数据缓存；
3. 如何在候选节点上计算缓存命中、区域亲和性、资源余量和负载惩罚；
4. 如何对比缓存无感知调度和边缘缓存感知调度；
5. 如何导出候选节点评分和请求级调度结果。

## 调度策略

样例包含两个策略：

```text
edge_round_robin     缓存无感知基线，按可行节点轮转
edge_cache_aware     边缘缓存感知调度，综合缓存、资源、区域和负载评分
```

## 调度评分

`edge_cache_aware` 使用最小综合评分：

```text
total_score = cache_score + resource_score + locality_score - load_penalty - latency_penalty
```

其中：

```text
cache_score       函数 warm 缓存、镜像缓存和数据缓存得分
resource_score    CPU 与内存空闲资源得分
locality_score    请求来源区域与函数偏好区域匹配得分
load_penalty      当前节点负载惩罚
latency_penalty   网络延迟惩罚
```

该公式用于演示机制，后续可以替换为论文第四章中的缓存状态与容量画像协同调度评分。

## 输出文件

运行结束后，结果会保存到：

```text
examples/edge_cache_scheduler/outputs/
```

主要包括：

```text
edge_cache_scheduling_result.csv
edge_cache_candidate_score.csv
edge_cache_policy_summary.csv
edge_cache_node_summary.csv
edge_cache_function_summary.csv
```

## 结果解读

重点查看：

```text
edge_cache_policy_summary.csv
```

其中包含：

```text
function_cache_hit_rate
image_cache_hit_rate
data_cache_hit_rate
avg_estimated_latency
total_cold_start_penalty
total_image_pull_penalty
total_data_fetch_penalty
```

再查看：

```text
edge_cache_candidate_score.csv
```

可以分析每个请求下每个候选节点的缓存命中与综合得分。

## 设计边界

本样例不直接调用 faas-sim 核心调度器，而是采用独立调度逻辑演示边缘缓存感知评分过程。这样可以避免不同 faas-sim 源码版本的接口差异影响样例运行。后续若要接入真实 faas-sim 调度流程，可将 `EdgeCacheAwareScheduler` 中的评分逻辑迁移到 `skippy` 调度器封装中。

## 后续扩展

该样例属于论文需求类功能样例。后续可以在此基础上继续扩展：

1. 将边缘缓存评分替换为论文中的正式调度评分；
2. 接入 `cache_decision` 和 `cache_aware_autoscaling` 输出；
3. 引入节点异构冷启动时间；
4. 区分函数实例缓存、镜像缓存和数据缓存的不同容量约束；
5. 与 faas-sim 的 FunctionReplica 调度流程集成。
