可以，后续我们自己补 examples 时，不要一上来把 15 类都铺开。建议整理成一个 **faas-sim 样例补齐 TODO 清单**，按“先服务你论文主线，再补框架完整性”的顺序推进。

# faas-sim examples 补齐 TODO 清单

## 一、统一样例工程规范

### TODO-00：统一新增样例目录规范

所有后续新增样例建议统一采用下面结构：

```text
examples/xxx_example/
├── main.py
├── README_CN.md
├── notebook/
│   └── xxx_首格代码自检版.ipynb
└── outputs/
    └── .gitkeep
```

其中：

```text
main.py              可直接命令行运行的标准样例入口
README_CN.md         中文说明，解释样例目标、运行方式、输出指标
notebook/            Jupyter 可运行版本，采用首格代码自检结构
outputs/             保存 CSV、图表或中间结果
```

Notebook 统一采用这套结构：

```text
第 1 格：最小代码自检，只 print，不导入 faas-sim
第 2 格：定位项目根目录
第 3 格：subprocess.run 执行原始 main.py
第 4 格：机制说明
第 5 格：后续指标分析建议
```

避免直接在 Notebook 里重写 `sim.run()`，也避免使用 `Popen + for line in process.stdout`。

验收标准：

```text
python -u examples/xxx_example/main.py 可以运行
Notebook 第 1 格有输出
Notebook 第 3 格能执行 main.py 并打印完整日志
README_CN.md 能说明样例目标、运行方式和关键指标
```

## 二、优先级 P0：论文主线强相关样例

这部分优先补，因为它们直接服务你的第三章、第四章和实验平台建设。

## TODO-01：冷启动与镜像缓存样例

目录建议：

```text
examples/cold_start/
examples/image_cache/
```

核心目标：

```text
明确展示函数冷启动过程
区分 deploy / startup / setup / invoke 阶段耗时
展示第一次镜像拉取和后续镜像复用的差异
分析镜像大小、网络带宽、节点位置对冷启动时间的影响
```

建议实现内容：

```text
1. 创建一个基础拓扑
2. 注册至少两个函数镜像，例如 small-image / large-image
3. 第一次部署函数，触发 docker.pull
4. 在同一节点再次部署同镜像函数，观察镜像缓存效果
5. 对比不同节点、不同镜像大小下的 deploy 时间
6. 提取 replica_deployment_df、flow_df、invocations_df
7. 统计 cold_start_time、image_pull_time、startup_time
```

关键指标：

```text
image_pull_time
startup_time
setup_time
first_invoke_time
warm_invoke_time
cold_start_time
flow_duration
```

预期输出：

```text
cold_start_events.csv
image_pull_events.csv
cold_vs_warm_summary.csv
```

对论文价值：

```text
支撑第三章冷启动建模
支撑函数实例缓存收益分析
支撑镜像缓存与实例缓存区别说明
```

## TODO-02：函数实例缓存策略样例

目录建议：

```text
examples/cache_policy/
```

核心目标：

```text
构建最小版函数实例缓存决策流程
展示 keep_warm / prewarm_candidate / scale_down_candidate 的基本逻辑
为第三章 R_cache、缓存效用和冷启动收益实验提供入口
```

建议实现内容：

```text
1. 定义函数访问记录
2. 统计函数请求次数、最近访问时间、平均冷启动时间
3. 定义缓存收益 cold_benefit
4. 定义资源成本 resource_cost
5. 计算 cache_utility
6. 根据阈值输出 keep_warm / prewarm_candidate / scale_down_candidate / observe
7. 将决策结果写入 cache_decision_df
```

建议先做简化版公式：

```text
cache_utility = cold_start_benefit - resource_cost
```

后续再扩展为正式论文模型。

关键指标：

```text
function_name
request_count
avg_inter_arrival
avg_cold_start
resource_cost
cache_utility
cache_decision
```

预期输出：

```text
cache_decisions.csv
cache_utility_summary.csv
```

对论文价值：

```text
对应第三章核心方法雏形
支撑函数画像到缓存决策的闭环
为后续实现 R_cache 提供实验骨架
```

## TODO-03：缓存状态感知调度样例

目录建议：

```text
examples/cache_aware_scheduler/
```

核心目标：

```text
展示调度器如何读取 warm replica / cached replica 状态
优先把请求或副本调度到已有热实例的节点
对比默认调度、随机调度和缓存感知调度
```

建议实现内容：

```text
1. 定义 CacheAwareScheduler
2. 从当前 FaaS 系统中读取函数副本状态
3. 判断某个函数在哪些节点已有 RUNNING 副本
4. 调度时优先选择已有热实例节点
5. 没有热实例时再根据资源或默认规则选择节点
6. 记录每次调度是否命中缓存
7. 与 random scheduler / default scheduler 对比
```

关键指标：

```text
cache_hit
selected_node
warm_replica_node
cold_start_count
avg_response_time
schedule_decision
```

预期输出：

```text
cache_aware_schedule_events.csv
cache_hit_summary.csv
scheduler_comparison.csv
```

对论文价值：

```text
对应第四章缓存状态感知协同调度
说明调度不只是选择资源空闲节点，还要考虑实例状态
支撑“缓存状态影响调度决策”的实验论证
```

## TODO-04：自动伸缩策略样例

目录建议：

```text
examples/autoscaling_policy/
```

核心目标：

```text
完整展示 faas-sim 中函数副本自动伸缩闭环
从负载变化到副本数变化，再到响应时间变化
为第四章 R_load 与 R_desired 提供 baseline 和扩展入口
```

建议实现内容：

```text
1. 配置 ScalingConfiguration
2. 设置 min_replicas / max_replicas
3. 启动 autoscaler 后台协程
4. 构造突增负载、平稳负载、下降负载
5. 周期性观察请求队列、RPS 或并发请求数
6. 触发 scale_up 和 scale_down
7. 记录副本数随时间变化
```

关键指标：

```text
time
function_name
current_replicas
desired_replicas
request_rate
in_flight_requests
scale_action
```

预期输出：

```text
autoscaling_events.csv
replica_timeline.csv
load_replicas_summary.csv
```

对论文价值：

```text
对应第四章 R_load
提供默认自动伸缩 baseline
便于后续扩展 R_desired = max(R_cache, R_load)
```

## TODO-05：批量实验样例

目录建议：

```text
examples/batch_experiment/
```

核心目标：

```text
把单次样例升级为可重复实验
支持多策略、多负载、多拓扑、多随机种子的批量运行
为后续论文出图和统计分析服务
```

建议实现内容：

```text
1. 定义实验配置列表
2. 支持 scheduler_name 参数
3. 支持 workload_name 参数
4. 支持 topology_name 参数
5. 支持 random_seed 参数
6. 循环运行多组 Simulation
7. 每组实验保存独立 CSV
8. 汇总生成 summary.csv
```

建议配置维度：

```text
scheduler: default / random / cache_aware
workload: low / medium / burst
topology: small_edge / urban_sensing / cloud_edge
seed: 1 / 2 / 3 / 4 / 5
```

关键指标：

```text
avg_response_time
p95_response_time
cold_start_count
cache_hit_rate
scale_action_count
resource_utilization
```

预期输出：

```text
experiment_runs.csv
summary.csv
comparison.csv
```

对论文价值：

```text
从单样例进入论文实验框架
支撑多轮重复实验和均值统计
为后续画图、表格和消融实验打基础
```

## 三、优先级 P1：faas-sim 核心机制补全样例

这部分用于补齐官方 examples 缺失的框架能力，增强你对 faas-sim 全部机制的掌控。

## TODO-06：自定义负载均衡器样例

目录建议：

```text
examples/custom_load_balancer/
```

核心目标：

```text
展示多个函数副本存在时，请求如何被路由到具体副本
```

建议策略：

```text
round_robin
random
least_loaded
nearest_node
cache_hit_first
```

关键指标：

```text
request_id
function_name
selected_replica
selected_node
load_balancer_policy
```

论文关联：

```text
为第四章请求路由、热实例命中和缓存状态感知调度做准备
```

## TODO-07：Skippy 完整调度能力样例

目录建议：

```text
examples/skippy_filters_scores/
```

核心目标：

```text
展示 Skippy 默认调度器的过滤、打分和 SchedulingResult 语义
```

建议覆盖：

```text
资源过滤
镜像本地性
数据本地性
节点可行性
needed_images
feasible_nodes
节点排名
```

关键指标：

```text
candidate_nodes
feasible_nodes
selected_node
needed_images
filter_reason
score
```

论文关联：

```text
为设计自己的调度器提供 baseline 理解
解释默认调度器与缓存感知调度的差异
```

## TODO-08：网络仿真与镜像拉取样例

目录建议：

```text
examples/network_flow/
examples/image_pull_network/
```

核心目标：

```text
单独展示 Ether 网络传输如何影响镜像拉取和函数启动
```

建议覆盖：

```text
节点间链路
链路带宽
链路延迟
镜像大小
多 flow 竞争
flow_df 分析
```

关键指标：

```text
flow_start
flow_finish
source_node
target_node
data_size
bandwidth
duration
```

论文关联：

```text
支撑边缘网络条件影响冷启动的实验分析
```

## TODO-09：资源监控样例

目录建议：

```text
examples/resource_monitor/
```

核心目标：

```text
展示 ResourceState 和 ResourceMonitor 如何记录节点资源使用情况
```

建议覆盖：

```text
invoke 阶段申请 CPU
invoke 阶段申请内存
请求结束后释放资源
周期性采集资源使用率
生成节点资源利用率曲线
```

关键指标：

```text
node_name
cpu_used
memory_used
cpu_utilization
memory_utilization
function_name
replica_id
```

论文关联：

```text
为缓存资源成本、节点压力和扩缩容策略提供指标基础
```

## TODO-10：性能 Oracle 与轨迹驱动模型样例

目录建议：

```text
examples/trace_oracle/
examples/performance_model/
```

核心目标：

```text
展示 faas-sim trace-driven 特性
用函数画像或执行时间轨迹驱动 FET 采样
```

建议覆盖：

```text
读取 profiling trace
构造 execution time oracle
按函数类型采样执行时间
按节点类型采样执行时间
记录 fets_df
替换固定 env.timeout
```

关键指标：

```text
sampled_fet
function_name
node_type
trace_source
execution_time
```

论文关联：

```text
为仿真与真实集群数据对齐提供基础
支撑异构节点上函数执行时间差异建模
```

## TODO-11：性能退化与多租户干扰样例

目录建议：

```text
examples/degradation/
examples/multitenancy/
```

核心目标：

```text
展示多个函数副本共用节点时的资源竞争和性能退化
```

建议覆盖：

```text
单函数单副本执行时间
多函数共节点执行时间
CPU 干扰
内存干扰
并发请求干扰
根据资源占用修正 FET
```

关键指标：

```text
concurrency
node_utilization
base_fet
degraded_fet
slowdown_ratio
```

论文关联：

```text
支撑缓存副本过多会增加节点资源压力这一论点
解释为什么缓存策略需要考虑资源成本
```

## 四、优先级 P2：实验场景扩展样例

这部分不是最先做，但后续完善实验平台时需要补。

## TODO-12：存储与数据本地性样例

目录建议：

```text
examples/storage_index/
examples/data_locality/
```

核心目标：

```text
展示函数请求依赖输入数据时，数据位置如何影响调度和传输耗时
```

建议覆盖：

```text
注册数据对象
声明数据所在节点
函数请求携带数据依赖
调度器优先靠近数据节点
统计数据传输耗时
```

论文关联：

```text
可作为缓存状态感知调度的扩展因素
当前不是最高优先级
```

## TODO-13：故障建模样例

目录建议：

```text
examples/fault_model/
```

核心目标：

```text
展示节点、链路、函数副本异常对请求执行的影响
```

建议覆盖：

```text
节点不可用
链路带宽下降
函数副本失败
请求失败
故障恢复
重新调度
```

论文关联：

```text
可作为系统鲁棒性扩展实验
当前不作为第三、四章主实验
```

## TODO-14：多拓扑场景样例

目录建议：

```text
examples/topologies/
```

核心目标：

```text
展示不同边缘拓扑如何影响调度、冷启动和网络传输
```

建议覆盖：

```text
single_node
small_edge_cluster
cloud_edge
urban_sensing
multi_region_edge
custom_heterogeneous_edge
```

论文关联：

```text
为仿真扩展实验提供场景基础
配合 batch_experiment 使用
```

## TODO-15：协同仿真与在线决策样例

目录建议：

```text
examples/cosimulation/
```

核心目标：

```text
展示 faas-sim 如何作为在线决策辅助引擎
```

建议覆盖：

```text
读取当前系统状态
试跑多个调度方案
试跑多个扩缩容方案
比较响应时间和资源消耗
选择最优方案
输出控制建议
```

论文关联：

```text
与真实 OpenFaaS advisor / executor 思路相关
适合作为后续扩展，不放在最早阶段
```

## 五、推荐实施顺序

建议我们后续按这个顺序补：

```text
第 1 轮：examples/cold_start/
第 2 轮：examples/cache_policy/
第 3 轮：examples/cache_aware_scheduler/
第 4 轮：examples/autoscaling_policy/
第 5 轮：examples/batch_experiment/
第 6 轮：examples/resource_monitor/
第 7 轮：examples/network_flow/
第 8 轮：examples/trace_oracle/
第 9 轮：examples/degradation/
第 10 轮：examples/custom_load_balancer/
第 11 轮：examples/skippy_filters_scores/
第 12 轮：examples/topologies/
第 13 轮：examples/data_locality/
第 14 轮：examples/fault_model/
第 15 轮：examples/cosimulation/
```

前 5 轮完成后，faas-sim 就能从“官方入门样例集”转成你论文需要的“边缘 Serverless 冷启动、实例缓存与协同调度实验平台”。

## 六、当前优先级总表

| 优先级 | 目录                                | 目标          | 论文关联        |
| --- | --------------------------------- | ----------- | ----------- |
| P0  | `examples/cold_start/`            | 冷启动与镜像缓存建模  | 第三章         |
| P0  | `examples/cache_policy/`          | 实例缓存策略      | 第三章         |
| P0  | `examples/cache_aware_scheduler/` | 缓存状态感知调度    | 第四章         |
| P0  | `examples/autoscaling_policy/`    | 自动伸缩闭环      | 第四章         |
| P0  | `examples/batch_experiment/`      | 批量实验框架      | 第五章/实验章     |
| P1  | `examples/resource_monitor/`      | 资源使用监控      | 第三/四章       |
| P1  | `examples/network_flow/`          | 网络传输与镜像拉取   | 第三章         |
| P1  | `examples/trace_oracle/`          | 轨迹驱动性能建模    | 实验校准        |
| P1  | `examples/degradation/`           | 性能退化与资源竞争   | 资源成本论证      |
| P1  | `examples/custom_load_balancer/`  | 请求路由策略      | 第四章扩展       |
| P1  | `examples/skippy_filters_scores/` | Skippy 调度机制 | baseline 理解 |
| P2  | `examples/topologies/`            | 多拓扑实验场景     | 仿真扩展        |
| P2  | `examples/data_locality/`         | 数据本地性       | 扩展实验        |
| P2  | `examples/fault_model/`           | 故障场景        | 鲁棒性扩展       |
| P2  | `examples/cosimulation/`          | 在线决策仿真      | 系统扩展        |

## 七、建议新增总 README

后续可以在 `examples/` 下新增：

```text
examples/README_CN.md
```

内容结构：

```text
1. 官方已有样例
2. 本项目扩展样例
3. 样例运行方式
4. Notebook 使用规范
5. 各样例对应论文问题
6. 各样例输出指标说明
7. 推荐学习顺序
```

这样后续你看项目时会非常清楚：

```text
哪些是官方原始 examples
哪些是我们为论文补的 examples
每个样例解决什么问题
每个样例输出什么指标
每个样例对应论文哪一章
```
