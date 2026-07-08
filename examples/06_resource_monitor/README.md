# 06_resource_monitor：faas-sim ResourceMonitor 资源监控样例

本样例演示 faas-sim 中 `ResourceState` 和 `ResourceMonitor` 的基本用法，重点展示函数执行期间如何登记 CPU / memory，执行结束后如何释放资源，以及如何把周期性资源采样与函数调用记录关联起来。

## 运行方式

在项目根目录运行：

```bash
python -u examples/06_resource_monitor/main.py
python -u examples/06_resource_monitor/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 PNG/PDF 到 `figures/`。

## 样例目标

1. 演示 `env.resource_state.put_resource()` / `remove_resource()`。
2. 演示 `ResourceMonitor` 如何周期性采集 per-replica CPU/memory 利用率。
3. 导出 `function_utilization.csv`、`invocations.csv`、`invoke_dispatch_probe.csv` 等原始指标。
4. 额外导出 `resource_monitor_sample_probe.csv`，从 `env.metrics_server` 读取真实 `ResourceWindow.time`，弥补原始 `function_utilization.csv` 缺少 simtime 的问题。
5. 生成 `invocation_resource_join.csv`，用真实采样 simtime 关联 invocation 执行窗口和资源采样。
6. 生成 `resource_monitor_invoke_probe_invocation_join.csv`，逐条验证 invoke probe 与 invocation 记录一致。

## 拓扑

最小 4-server 拓扑：

```text
internet -- registry_link(200 Mbps) -- switch -- link_server_X(200 Mbps) -- server_X
```

本样例关注 CPU/memory 监控，不关注网络瓶颈。两个函数副本由默认 Skippy 调度到 `server_0`。

## 工作负载

| 函数 | 镜像 | 副本数 | 请求数 | RPS | invoke 时长 |
|---|---|---:|---:|---:|---:|
| resource-heavy-python-pi | resource-heavy-python-pi-cpu | 2 | 12 | 3 | 1.5s |

`main.py` 会等待两个副本都进入 `RUNNING` 后再触发请求，避免负载只压到第一个副本。

## 资源占用

`simulator.py` 在每次 invoke 开始时登记：

| 资源 | 数值 |
|---|---:|
| CPU | 节点 CPU 容量 × 35% = 1400 millis |
| memory | 128 MiB |

同一 replica 上多个并发请求会叠加。因此当前输出中单个 replica 的峰值 CPU util 为 `1.05`，表示该 replica 在某个采样点上叠加了约 3 个并发请求。

## 输出文件

运行结束后，结果保存到 `examples/06_resource_monitor/outputs/`：

```text
function_utilization.csv                          # ResourceMonitor 原始 per-replica 资源采样，time 是 wall clock
resource_monitor_sample_probe.csv                 # 样例新增：真实 simtime 资源采样
node_utilization.csv                              # 节点级资源采样；当前 faas-sim 版本为空
invocations.csv                                   # 12 次调用记录，含 t_start/t_exec
invoke_dispatch_probe.csv                         # simulator invoke 派发探针
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
resource_utilization_per_replica.csv              # 每个 replica 的资源聚合
invocation_resource_join.csv                      # invocation 执行窗口 × ResourceMonitor 采样
resource_monitor_invoke_probe_invocation_join.csv # invoke probe × invocations 逐条 join
resource_monitor_summary.csv                      # 总体资源摘要
resource_monitor_invocation_summary.csv           # 调用摘要
resource_monitor_paper_highlight.csv              # 论文 demo 关键指标
resource_monitor_self_check.csv                   # 10 项 self-check
```

绘图输出到 `examples/06_resource_monitor/figures/`：

```text
fig01_per_invocation_cpu_util.png/pdf
fig02_per_replica_util.png/pdf
fig03_cpu_util_timeline.png/pdf
fig04_paper_highlight_metrics.png/pdf
```

## 关键结果

### Resource Summary

| metric | value |
|---|---:|
| total_resource_samples | 12 |
| monitored_replicas | 2 |
| monitored_nodes | 1 |
| overall_avg_cpu_util | 0.583333 |
| overall_max_cpu_util | 1.05 |
| overall_avg_mem_util | 0.104167 |
| overall_max_mem_util | 0.1875 |
| invocation_events | 12 |
| join_coverage | 1.0 |
| join_sample_coverage | 1.0 |
| invoke_probe_join_match_ratio | 1.0 |

`join_coverage=1.0` 表示 `invocation_resource_join.csv` 对 12 次调用都生成了行。`join_sample_coverage=1.0` 表示 12/12 个调用窗口内至少包含一个真实 ResourceMonitor 采样点。

### Per-Replica Summary

当前两个副本资源分布对称：

| samples | avg_cpu_util | max_cpu_util | avg_mem_util | max_mem_util |
|---:|---:|---:|---:|---:|
| 6 | 0.583333 | 1.05 | 0.104167 | 0.1875 |
| 6 | 0.583333 | 1.05 | 0.104167 | 0.1875 |

### Probe Join

`resource_monitor_invoke_probe_invocation_join.csv` 逐条验证：

- `probe_simtime == inv_t_start`
- `probe_node == inv_node`
- 行数 == 12

当前 `invoke_probe_join_match_ratio = 1.0`。

## Self-Check

`main.py` 运行后应输出 `data self-check: 10 / 10 PASS`：

| check_id | 含义 |
|---|---|
| 01_total_resource_samples_at_least_10 | 至少采到 10 条资源样本 |
| 02_monitored_replicas_is_2 | 采样覆盖 2 个副本 |
| 03_overall_max_cpu_util_above_0.5 | 确实采到明显 CPU 使用 |
| 04_invocations_count_is_12 | 调用数为 12 |
| 05_join_rows_equals_invocations | resource join 行数等于调用数 |
| 06_resource_join_has_samples | 调用窗口包含资源采样 |
| 07_per_replica_rows_is_2 | per-replica 聚合有 2 行 |
| 08_per_replica_samples_sum_matches | per-replica 样本数之和等于总样本数 |
| 09_invoke_dispatch_probe_events_is_12 | invoke probe 行数为 12 |
| 10_invoke_probe_join_consistent | probe 与 invocations 逐条一致 |

## 图表说明

- `fig01_per_invocation_cpu_util`：每次 invoke 执行窗口内的平均/峰值 CPU util。
- `fig02_per_replica_util`：两个副本的 CPU/memory 平均和峰值利用率。
- `fig03_cpu_util_timeline`：使用 `resource_monitor_sample_probe.csv` 的真实 simtime，按 replica 展示 ResourceMonitor 周期采样，参考线为 1/2/3 个并发请求的 CPU util。
- `fig04_paper_highlight_metrics`：只展示适合横向比较的比例类指标。

## 文件说明

- `main.py`：创建拓扑、部署 2 个副本、等待副本 running、触发 12 次请求并导出结果。
- `simulator.py`：在 invoke 阶段登记/释放 CPU 和 memory，并写入 `invoke_dispatch_probe`。
- `analysis.py`：导出真实 simtime 资源采样、资源聚合、调用关联、probe join、paper highlight 和 self-check。
- `plot.py`：读取输出 CSV，生成 4 张论文 demo 图。

## 论文叙事点

12 次 invoke 在 2 个 replica 上执行，每次请求登记 1400 millis CPU 和 128 MiB memory。ResourceMonitor 采到 12 条真实 simtime per-replica 样本，两个副本各 6 条；峰值 CPU util 为 1.05，表示单个副本上约 3 个请求并发叠加。`invocation_resource_join.csv` 对 12 次调用全部建行，且 12 次调用窗口都包含资源采样点；`resource_monitor_invoke_probe_invocation_join.csv` 进一步验证 invoke 派发探针与 invocation 记录 100% 一致。
