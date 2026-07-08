# 02_load_balancer：faas-sim 原生负载均衡样例

本样例用于演示 faas-sim 在多个 RUNNING 副本之间的负载均衡行为。样例部署一个固定 3 副本函数，触发 30 个请求，并使用可观测的轮询负载均衡器记录每次 `next_replica()` 的路由选择。输出包含原始指标、路由序列、逐请求 route×probe×invocation 关联、论文 demo 摘要、自洽检查和 4 张图。

## 运行方式

在项目根目录运行：

```bash
python -u examples/02_load_balancer/main.py
```

运行结束后会生成 `examples/02_load_balancer/outputs/` 下的 CSV，并打印 `10 / 10 PASS` 的 self-check。

生成论文 demo 图：

```bash
python -u examples/02_load_balancer/plot.py
```

可选参数：

```bash
python -u examples/02_load_balancer/plot.py --input-dir <outputs目录> --output-dir <figures目录>
```

默认输出到 `examples/02_load_balancer/figures/`：

- `fig01_routing_sequence_staircase.png` + `.pdf`：request_id -> replica_index 的轮询序列图，论文 demo 最核心。
- `fig02_replica_routing_distribution.png` + `.pdf`：每个副本收到的请求数。
- `fig03_cumulative_replica_requests.png` + `.pdf`：每个副本的累计请求曲线。
- `fig04_paper_highlight_metrics.png` + `.pdf`：关键指标条形图。

## 样例目标

1. 演示 faas-sim 何时调用负载均衡器选择目标副本。
2. 演示 3 个 RUNNING 副本下的严格轮询选择序列：`0,1,2,0,1,2,...`。
3. 演示如何替换 `DefaultFaasSystem.load_balancer`，保留轮询语义并增加可观测指标。
4. 导出 `load_balancer.csv`，记录每次路由的 request_id、simtime、replica_index、selected_replica_id。
5. 导出逐请求 route×probe×invocation 关联表，验证路由选择、模拟器入口和最终 invocation 记录一致。
6. 用 self-check 验证 30 个请求均匀分配到 3 个副本，每个副本 10 次。

## 输出文件

运行结束后，结果保存到：

```text
examples/02_load_balancer/outputs/
```

主要文件：

```text
load_balancer.csv                              # 每次负载均衡路由决策
load_balancer_routing_sequence.csv             # 按 request_id 排序的路由序列
load_balancer_summary.csv                      # 路由事件数、均衡度、连续同副本次数等摘要
load_balancer_replica_distribution.csv         # 每个 replica 的路由次数分布
load_balancer_probe_invocation_join.csv        # 逐请求 route×probe×invocation 关联证据
load_balancer_paper_highlight.csv              # 论文 demo 关键指标
load_balancer_self_check.csv                   # 10 项数据自检
invoke_dispatch_probe.csv                      # simulator.invoke 入口 probe
invocations.csv                                # faas-sim 实际 invocation 记录
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

## 关键输出

### load_balancer_routing_sequence.csv

该文件是核心图的数据源：

| request_id | simtime | replica_index | running_replicas | selected_node | policy |
|---:|---:|---:|---:|---|---|
| 1 | 3.05 | 0 | 3 | server_0 | instrumented_round_robin |
| 2 | 3.10 | 1 | 3 | server_0 | instrumented_round_robin |
| 3 | 3.15 | 2 | 3 | server_0 | instrumented_round_robin |
| 4 | 3.20 | 0 | 3 | server_0 | instrumented_round_robin |
| 5 | 3.25 | 1 | 3 | server_0 | instrumented_round_robin |
| 6 | 3.30 | 2 | 3 | server_0 | instrumented_round_robin |

可以直接看到严格轮询顺序 `0,1,2` 周期重复。

### load_balancer_replica_distribution.csv

| replica_index | routed_requests |
|---:|---:|
| 0 | 10 |
| 1 | 10 |
| 2 | 10 |

所有请求均匀分配到 3 个副本，`balance_std=0`，`balance_ratio=1.0`。

### load_balancer_probe_invocation_join.csv

该文件现在是逐请求证据表，而不是只有一行汇总。关键列：

| column | meaning |
|---|---|
| `request_id` | 请求 ID |
| `replica_index` | 负载均衡器选择的轮询索引 |
| `replica_id` | simulator.invoke 入口看到的副本 ID |
| `selected_replica_id` | load_balancer 记录的副本 ID |
| `route_simtime` | load_balancer 路由时间 |
| `simtime` | invoke probe 时间 |
| `inv_t_start` | invocations.csv 中的实际执行开始时间 |
| `expected_t_exec` | simulator 预期执行时间，当前为 0.3 |
| `inv_t_exec` | invocations.csv 中实际记录的执行时间 |
| `matched` | 上述 route/probe/invocation 是否全部一致 |

当前 30 行全部 `matched=True`。

### load_balancer_paper_highlight.csv

当前关键指标为：

| metric | value |
|---|---:|
| route_events | 30 |
| invocation_events | 30 |
| selected_replica_count | 3 |
| selected_node_count | 1 |
| max_routed_requests | 10 |
| min_routed_requests | 10 |
| balance_std | 0.0 |
| balance_ratio_min_over_max | 1.0 |
| adjacent_switch_rate | 1.0 |
| route_probe_invocation_total_match | True |
| route_probe_invocation_all_match | True |
| probe_invocation_t_exec_match_rate | 1.0 |

`selected_node_count=1` 是当前默认调度器把 3 个副本都放到 `server_0` 的真实结果。本样例演示的是“多个函数副本之间的请求选择”，不是跨节点流量分散。

## 自洽检查

`load_balancer_self_check.csv` 包含 10 项检查：

```text
01_route_equals_invocation
02_three_replicas_routed
03_per_replica_get_10_requests
04_balance_ratio_is_one
05_balance_std_is_zero
06_max_routed_equals_10
07_min_routed_equals_10
08_strict_round_robin_switch
09_route_probe_invocation_total_match
10_route_probe_invocation_all_match
```

当前运行结果为 `10 / 10 PASS`。

## 文件说明

- `main.py`：创建最小 4-server 拓扑、部署 3 副本函数、触发 30 个请求并导出结果。
- `system.py`：创建 `DefaultFaasSystem`，并替换为可观测轮询负载均衡器。
- `load_balancer.py`：实现 `InstrumentedRoundRobinLoadBalancer`，记录每次路由决策。
- `simulator.py`：固定执行时间 0.3s，并在 `invoke` 入口记录 `invoke_dispatch_probe`。
- `analysis.py`：导出原始指标、构建路由序列、分布表、逐请求 join、自洽检查和论文摘要。
- `plot.py`：生成 4 张 PNG/PDF 图，支持 `--input-dir` 和 `--output-dir`。

## 论文 demo 一段话总结

在固定 3 个 RUNNING 副本、30 个请求的负载均衡实验中，faas-sim 通过轮询策略按 `0,1,2` 周期选择副本。每个副本恰好处理 10 个请求，副本级请求数标准差为 0，min/max 均衡比为 1.0，相邻请求切换副本比例为 1.0。逐请求 route×probe×invocation 关联显示，负载均衡器选择的副本、模拟器实际执行入口和 `invocations.csv` 最终记录 100% 一致。
