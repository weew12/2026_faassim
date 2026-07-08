# 03_skippy_scheduler：faas-sim 原生 Skippy 调度机制样例

本样例用于演示 faas-sim 中 Skippy 默认调度器的完整过程：资源谓词过滤、可行节点集合、节点选择、镜像缓存复用、调度结果导出、probe×invocation 一致性检查，以及论文 demo 图表。

## 运行方式

在项目根目录运行：

```bash
python -u examples/03_skippy_scheduler/main.py
python -u examples/03_skippy_scheduler/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 PNG/PDF 到 `figures/`。

## 样例目标

1. 演示 `DefaultFaasSystem` 如何调用 Skippy 调度器为函数副本选择节点。
2. 用异构节点资源展示 `PodFitsResourcesPred` 的过滤效果。
3. 解释 `SchedulingResult.suggested_host`、`feasible_nodes`、`needed_images` 的含义。
4. 展示镜像缓存复用：同一镜像第二个 pod 调度到已缓存节点时 `needed_images_count=0`。
5. 导出候选节点快照、调度结果、节点分布、论文关键指标和自检结果。
6. 用 `invoke_dispatch_probe` 与 `invocations.csv` 做逐条 join，验证 simulator dispatch 与 faas-sim invocation 记录一致。

## 拓扑

本样例使用 4-server 异构拓扑，避免城市感知场景内部状态污染，同时让资源过滤效果可见：

```text
internet -- registry_link -- switch -- link_server_X -- server_X
```

| 节点 | arch | CPU | Memory | 设计目的 |
|---|---|---:|---:|---|
| server_0 | x86 | 4000m | 2Gi | 可承载 large pod |
| server_1 | x86 | 1600m | 1Gi | 可承载 medium pod |
| server_2 | x86 | 1600m | 1Gi | 可承载 medium pod |
| server_3 | x86 | 600m | 512Mi | 只适合 small pod |

## 工作负载

| 函数 | 镜像 | CPU | Memory | 副本数 | 请求数 |
|---|---|---:|---:|---:|---:|
| skippy-large | skippy-large-cpu | 1700m | 1536Mi | 1 | 8 |
| skippy-medium | skippy-medium-cpu | 900m | 768Mi | 2 | 12 |
| skippy-small | skippy-small-cpu | 50m | 64Mi | 2 | 20 |

部署顺序为 `large -> medium -> small`，这样 large 首先展示“只有 1 个可行节点”，medium 展示资源过滤后的中等可行集合，small 展示全节点可行和镜像缓存复用。

## 输出文件

运行结束后，结果保存到 `examples/03_skippy_scheduler/outputs/`：

```text
skippy_scheduler_result.csv              # 每个 pod 的 SchedulingResult
skippy_scheduler_candidate.csv           # 每个 pod × 每个候选节点的资源/谓词快照
schedule_probe.csv                       # 调度前后 probe，每个 pod 两行
schedule.csv                             # faas-sim 原生 schedule 事件
allocation.csv                           # 分配事件
function_deployments.csv                 # 函数部署记录
function_deployment_lifecycle.csv        # 函数部署生命周期
function_replicas.csv                    # 函数副本记录
replica_deployment.csv                   # 副本部署生命周期
invocations.csv                          # 40 次实际 invoke
flow.csv                                 # 镜像拉取/网络流
invoke_dispatch_probe.csv                # simulator dispatch probe，40 行
skippy_feasible_nodes_per_pod.csv        # 每个 pod 的 all/feasible/selected_node
skippy_node_scheduling_stats.csv         # 每个 node 被调度到的 pod 数
skippy_scheduler_summary.csv             # 调度摘要
skippy_selected_node_distribution.csv    # selected_node × needed_images 分布
skippy_invoke_probe_invocation_join.csv  # dispatch probe × invocations 逐条 join
skippy_schedule_probe_invocation_join.csv # 调度/dispatch/invocation 汇总一致性
skippy_paper_highlight.csv               # 论文 demo 关键指标
skippy_self_check.csv                    # 10 项 self-check
```

绘图输出到 `examples/03_skippy_scheduler/figures/`：

```text
fig01_pods_per_node.png/pdf
fig02_feasible_nodes_per_pod.png/pdf
fig03_schedule_timeline.png/pdf
fig04_paper_highlight_metrics.png/pdf
```

## 关键结果

### 调度结果

当前输出中 5 个 pod 的可行节点数量如下：

| pod_name | all_nodes | feasible_nodes_full | needed_images_count | selected_node |
|---|---:|---:|---:|---|
| pod-skippy-large-1 | 4 | 1 | 1 | server_0 |
| pod-skippy-medium-1 | 4 | 2 | 1 | server_1 |
| pod-skippy-medium-2 | 4 | 1 | 1 | server_2 |
| pod-skippy-small-1 | 4 | 4 | 1 | server_3 |
| pod-skippy-small-2 | 4 | 4 | 0 | server_3 |

这能直接说明三件事：

- 资源过滤生效：`feasible_nodes_full` 从 1 到 4 不等。
- 节点选择有分布：5 个 pod 分布到 4 个节点。
- 镜像缓存复用可见：`pod-skippy-small-2` 调度到已有 small 镜像的 `server_3`，因此 `needed_images_count=0`。

### Paper Highlight

| metric | value |
|---|---:|
| total_pods_scheduled | 5 |
| invocation_events | 40 |
| selected_node_count | 4 |
| all_nodes | 4 |
| max_feasible_nodes | 4 |
| min_feasible_nodes | 1 |
| avg_feasible_nodes_full | 2.4 |
| pods_with_filtered_nodes | 3 |
| filtered_candidate_nodes | 8 |
| pods_with_needed_images | 4 |
| pods_with_cached_image | 1 |
| schedule_entropy | 1.9219 |
| probe_invocation_consistent | True |

### Self-Check

`main.py` 运行后应输出 `data self-check: 10 / 10 PASS`：

| check_id | 含义 |
|---|---|
| 01_total_pods_is_5 | 5 个 pod 全部被调度 |
| 02_invocation_events_is_40 | 40 次 invoke 全部完成 |
| 03_selected_node_at_least_1 | 至少有 1 个节点被选中 |
| 04_all_pods_have_feasible_nodes | 每个 pod 至少有 1 个可行节点 |
| 05_all_selected_node_recorded | selected_node 全部记录 |
| 06_resource_filtering_observed | 至少一个 pod 发生资源过滤 |
| 07_needed_and_cached_images_observed | 同时观察到镜像拉取和缓存复用 |
| 08_feasible_per_pod_rows_match | feasible_per_pod 行数与调度结果一致 |
| 09_node_scheduling_stats_nonempty | 节点调度统计非空 |
| 10_probe_invocation_consistent | schedule/dispatch/invocation 事件一致 |

## 图表说明

- `fig01_pods_per_node`：展示 pod 分布到哪些节点，适合说明调度结果。
- `fig02_feasible_nodes_per_pod`：堆叠展示 feasible 和 filtered 节点数，是本样例最关键的资源过滤图。
- `fig03_schedule_timeline`：展示 pod 调度顺序、simtime、目标节点和是否需要拉镜像。
- `fig04_paper_highlight_metrics`：展示论文 demo 关键数值，跳过布尔指标。

## 文件说明

- `main.py`：创建异构拓扑、注册三类函数、运行 workload 并导出结果。
- `scheduler.py`：继承 Skippy 原生 `Scheduler`，保留默认调度语义，只增加 candidate/result/probe 指标。
- `simulator.py`：固定 invoke 执行时间 0.25s，并写入 `invoke_dispatch_probe`。
- `analysis.py`：导出 CSV、构建摘要、执行 probe join 和 self-check。
- `plot.py`：读取 CSV，生成 4 张论文 demo 图。
