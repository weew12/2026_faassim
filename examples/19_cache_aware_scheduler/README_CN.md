# cache_aware_scheduler：缓存状态感知调度样例

本样例用于演示缓存状态感知调度的最小实验闭环。调度器读取节点级函数 warm 实例缓存状态，在候选节点中优先选择已有目标函数缓存的节点，从而降低冷启动惩罚。

## 运行方式

将 `cache_aware_scheduler/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/cache_aware_scheduler/main.py
```

## 文件结构

```text
cache_aware_scheduler/
├── inputs/
│   ├── cache_state_snapshot.csv
│   └── workload.csv
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── benchmark.py
├── cache_state.py
├── main.py
├── README_CN.md
├── scheduler.py
├── simulator.py
└── workload.py
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
examples/cache_aware_scheduler/outputs/
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

## 后续扩展

该样例属于论文需求类功能样例。后续可以在此基础上继续扩展：

1. 将 cache-aware score 替换为论文中的调度评分；
2. 接入 `cache_decision` 输出的 keep_warm / prewarm 结果；
3. 将节点画像、资源余量和冷启动时间纳入统一评分；
4. 支持多副本调度和容量约束；
5. 与 `cache_aware_autoscaling` 组合形成调度与扩缩容协同实验。


## 运行卡住排查

如果日志停在 `poll_available_replica`，通常说明某个函数副本没有进入可用状态。常见原因包括：

```text
当前 Python 导入了 site-packages 中的旧 sim 包，而不是项目本地 sim 包
调度器未能为 Pod 选择可用节点
资源请求过大，导致后续函数副本长期 Pending
```

本样例已在 `main.py` 中优先加入项目根目录到 `sys.path`，并在 `benchmark.py` 中为副本可用等待加入超时保护，避免无提示地长时间等待。


## 本版修复说明

为避免样例在默认 Skippy 资源过滤或内部队列状态下出现某个副本长期 Pending，本版将对照组改为稳定的 `CacheBlindScheduler`。该调度器不读取缓存状态，只按 server 节点轮转放置副本，重点用于和 `CacheAwareScheduler` 对比“是否使用函数实例缓存状态”这一变量。


## 第三版修复说明

此前版本为了简化镜像注册，让多个函数共用同一个镜像名 `cache-aware-shared-cpu`。但当前 faas-sim 的 `scale_up()` 会按 container image 统计已部署副本数；当多个函数共用同一镜像且各自 `scale_max=1` 时，第三个函数开始可能不会再创建副本，最终表现为 `poll_available_replica` 超时。

本版已改为每个函数使用独立镜像名，例如：

```text
fft-cache-aware-cpu
img-resize-cache-aware-cpu
json-parse-cache-aware-cpu
ml-infer-cache-aware-cpu
```

这样可以避免镜像级副本计数干扰函数级部署流程。


## 第四版修复说明

当前 faas-sim 版本中的 `FunctionRequest` 构造函数只接受函数名和可选请求大小，不支持 `request_id=...` 关键字参数。本版已改为先按原生方式创建请求对象：

```text
SimFunctionRequest(function_name)
```

再覆盖 `request_id` 字段，使输出结果仍然能够对应 `inputs/workload.csv` 中的请求编号。


## 第五版修复说明

当前 faas-sim 版本中的 `DefaultFaasSystem.invoke()` 只接收一个 `FunctionRequest` 参数，函数名从 `request.name` 中读取。因此本版已将调用方式从：

```text
env.faas.invoke(deployment, sim_request)
```

修正为：

```text
env.faas.invoke(sim_request)
```

该修改与当前源码中的 `DefaultFaasSystem.invoke(self, request)` 保持一致。
