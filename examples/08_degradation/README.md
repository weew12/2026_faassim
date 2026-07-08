# 08_degradation：faas-sim 性能退化样例

本样例演示函数执行过程中的**性能退化建模**。核心思想是：当同一节点上已有请求正在执行时，新到达请求会受到资源竞争影响，其执行时间被放大。

## 运行方式

在项目根目录运行：

```bash
python -u examples/08_degradation/main.py
python -u examples/08_degradation/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 png+pdf 到 `figures/`。

## 样例目标

该样例主要回答以下问题：

1. 如何利用 `node.current_requests` 观察节点当前并发负载；
2. 多个请求共节点执行时如何构造性能退化；
3. 如何将基础执行时间放大为退化后的执行时间；
4. 如何记录每次请求的退化因子；
5. **如何验证 simulator 派发的 final_duration 就是 faas-sim 记录的实际执行时间**（论文 demo 关键证据）。

## 退化模型

样例使用线性节点竞争退化模型：

```text
final_duration = base_duration * (1 + alpha * max(active_requests_before, 0))
```

| 参数 | 默认值 | 含义 |
|---|---|---|
| base_duration | 0.4 simtime 秒 | 无竞争时的基础执行时间 |
| active_requests_before | 0-29 | 本请求加入 node.current_requests 之前节点上已有的并发请求数 |
| alpha | 0.35 | 每个并发请求带来的执行时间放大系数 |
| final_duration | 0.40-4.46 | 退化后的本次请求执行时间 |

> **关键设计点**：`active_requests_before` 在 `node.current_requests.add(request)` **之前** 读取，
> 表示"该请求到达时节点上已有多少请求在跑"，不是"包含自己"。

## 拓扑

**最小 4-server 拓扑**（与 02-07 一致风格）：

```
internet ── registry_link(200Mbps) ── switch ── link_server_X(200Mbps) ── server_X (X=0..3)
                    └── DockerRegistry
```

**FixedNodeScheduler 强制 3 个副本全部分配到 server_0**，稳定触发共节点并发。

## 实验设计

| 参数 | 值 |
|---|---|
| 函数 | degradation-python-pi |
| cpu / mem | 150m / 128Mi |
| 副本数 | 3 |
| rps | 18（高并发率制造请求重叠） |
| max_requests | 40 |
| 峰值 active_requests_before | 29 |
| 峰值 final_duration | 4.46s |

## 输出文件

运行结束后，结果会保存到 `outputs/`：

```text
# 11 个 faas-sim / probe 内置 metric 的 CSV
degradation_probe.csv                  # 每次请求的退化采样（40 行）
invocations.csv                        # 实际函数调用事件（40 行）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
function_utilization.csv               # ResourceMonitor 周期性采集
node_utilization.csv                   # 节点级（本样例 0 行）
invoke_dispatch_probe.csv              # invoke 派发探针（仿 02-07 模式）

# 论文 demo 关键导出
degradation_summary.csv                # 按 (function_name, node_name) 聚合
degradation_concurrency_distribution.csv # 按 active_requests_before 分组（论文 demo 关键图）
degradation_invoke_join.csv            # 论文 demo 关键：degradation_probe × dispatch_probe × invocations 三表关联
degradation_model_consistency.csv      # 退化公式数学一致性（max_abs_diff=0）
degradation_paper_highlight.csv        # 论文 demo 关键摘要（13 条 metric/value）
degradation_self_check.csv             # 数据自检（10 项 PASS/FAIL）
```

`invocations.csv` 本身不包含 `request_id`。因此 `degradation_invoke_join.csv` 以 `invoke_dispatch_probe.csv` 作为桥接表：先按 `request_id` 关联 `degradation_probe`，再按 `(function_name, replica_id, simtime/t_start)` 关联 `invocations.csv`。

绘图脚本生成 4 张图到 `figures/`：

```text
fig01_concurrency_vs_duration.png/pdf   # 并发数 vs 执行时间（含理论曲线）
fig02_concurrency_distribution.png/pdf # 每个并发级别出现次数柱状图
fig03_per_request_degradation.png/pdf  # 每条请求的 active_before 和 final_duration 时序
fig04_paper_highlight_metrics.png/pdf  # 论文 demo 关键摘要指标条形图
```

## 论文 demo 关键摘要（13 条 paper highlight）

| metric | value | note |
|---|---|---|
| probe_count | 40 | degradation_probe 总采样数（应 == invocation_events） |
| invocation_events | 40 | 实际函数调用事件数（应 == 40） |
| base_duration | 0.4 | 无竞争基础执行时间（simtime 秒） |
| alpha | 0.35 | 每个并发请求引入的执行时间放大系数 |
| max_active_requests_before | 29 | peak 并发负载（峰值 29） |
| max_degradation_factor | 11.15 | peak 退化因子（应 == 1 + alpha × max_active = 11.15） |
| max_final_duration | 4.46 | peak 退化后执行时间（应 ≈ 4.46s，证明退化生效） |
| avg_final_duration | 2.535 | 平均退化后执行时间 |
| duration_match_count | 40 | degradation_probe.final_duration 与 inv t_exec 一致的行数（应 == 40） |
| duration_match_ratio | 1.0 | duration_match 比例（应 == 1.0） |
| max_abs_diff | 0.0 | 退化公式 final = base × (1 + alpha × active) 的 max abs diff（应 == 0） |
| concurrency_levels | 30 | degradation_concurrency_distribution 的不同 active_before 值数量 |
| probe_equals_invocations | True | probe_count == invocation_events（probe×invocation 一致） |

## 10 项数据自检（10 / 10 PASS）

| check_id | 含义 |
|---|---|
| 01_probe_count_is_40 | degradation_probe 行数 == 40 |
| 02_invocations_is_40 | invocations 行数 == 40 |
| 03_join_rows_is_40 | degradation_invoke_join 行数 == 40 |
| 04_all_duration_and_dispatch_match_true | duration/simtime/node 三类匹配全部为 True |
| 05_max_abs_diff_zero | 数学一致性 max_abs_diff < 1e-9 |
| 06_max_active_at_least_3 | max_active_requests_before >= 3（至少 3 个副本） |
| 07_max_final_greater_than_base | max_final_duration > base_duration × 2（证明退化生效） |
| 08_concurrency_levels_at_least_5 | concurrency_distribution 行数 >= 5 |
| 09_probe_equals_invocations | probe_count == invocation_events |
| 10_paper_self_consistent | paper_highlight 数字与 summary 一致 |

## 文件说明

### `main.py`

样例主入口。职责包括：

1. 创建 4-server 拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造 3 副本函数部署；
5. 使用固定节点调度器制造共节点并发；
6. 运行请求负载（rps=18, max_requests=40）；
7. **轮询 `env.metrics.records` 直到所有 40 次 invoke 完成**（替代原 `env.timeout(3)` 硬等待）；
8. 导出退化和调用结果指标 + 论文 demo 关键摘要 + 数据自检。

### `degradation_model.py`

性能退化模型文件。提供：

- `LinearNodeContentionDegradationModel`：final = base × (1 + alpha × active)
- `DegradationSample`：单次退化采样结果

### `simulator.py`

函数生命周期模拟器文件。提供 `DegradationFunctionSimulator`：

- `deploy()` 调用 `docker.pull()`，与普通函数部署一致；
- `startup()` 固定 0.2s；
- `invoke()` 读取 active_requests_before → 计算退化 → 写 `degradation_probe` 探针 + `invoke_dispatch_probe` 探针 → yield final_duration；
- `setup()` / `teardown()` 0s。

### `scheduler.py`

固定节点调度器文件。提供 `FixedNodeScheduler`，把 3 个副本固定部署到同一节点 `server_0`。

### `analysis.py`

指标导出与分析文件。负责：

- 导出 11 个 faas-sim / probe 内置 metric 的 CSV（含 invoke_dispatch_probe）
- 生成 `degradation_summary`（按 function × node 聚合）
- 生成 `degradation_concurrency_distribution`（按 active_requests_before 分组）
- 生成 `degradation_invoke_join`（degradation_probe × invoke_dispatch_probe × invocations 三表关联）
- 生成 `degradation_model_consistency`（退化公式数学一致性）
- 生成 `degradation_paper_highlight`（13 条论文 demo 关键摘要）
- 生成 `degradation_self_check`（10 项数据自检）

### `plot.py`

绘图脚本。读 `outputs/` CSV，输出 `figures/` 下 4 张 png+pdf：

1. **fig01_concurrency_vs_duration** —— 并发数 vs 执行时间（含理论曲线 `0.4 × (1 + 0.35 × active)`）
2. **fig02_concurrency_distribution** —— 每个并发级别出现次数
3. **fig03_per_request_degradation** —— 每条请求的 active_before 和 final_duration 时序（双子图）
4. **fig04_paper_highlight_metrics** —— 论文 demo 关键摘要条形图

### `outputs/`

CSV 输出目录。

### `figures/`

绘图输出目录（运行 plot.py 后生成）。

## 论文叙事点

> **"线性节点竞争退化模型 `final = 0.4 × (1 + 0.35 × active_requests_before)` 在 40 次 invoke 中 100% 一致执行：mathematical consistency `max_abs_diff = 0.0`、simulator 与 faas-sim 的 `duration_match = 1.0`、probe×invocation 完全匹配。共节点并发峰值达 29，最终执行时间从 0.4s 放大到 4.46s（11.15× 退化因子）。"**

## 08 vs 02-07 demo 价值对比

| 维度 | 02_load_balancer | 03_skippy_scheduler | 04_network_flow | 05_image_pull_network | 06_resource_monitor | 07_trace_oracle | 08_degradation |
|---|---|---|---|---|---|---|---|
| 仿真引擎 | faas-sim | faas-sim | Ether | faas-sim + docker | faas-sim + ResourceMonitor | faas-sim + Trace Oracle | faas-sim + Degradation Model |
| 拓扑 | 4-server 最小 | 4-server 最小 | 边缘→云端 | 4-server + 1Gbps | 4-server 最小 | 4-server 最小 | 4-server 最小 |
| 关注对象 | FunctionReplica 路由 | Pod 调度 | 网络 Flow | 镜像拉取 + 缓存 | CPU/内存利用率 | trace-driven 执行时间 | **节点竞争退化** |
| 数据来源 | 合成 (固定 0.3s) | 合成 (固定 0.25s) | 合成 (Flow 模型) | 合成 (固定 0.05s) | 合成 (固定 1.5s) | CSV trace | **节点并发数** |
| 探针 | invoke_dispatch_probe | schedule_probe + invoke_dispatch_probe | （不适用） | image_pull_probe + invoke_dispatch_probe | function_utilization + invoke_dispatch_probe | trace_oracle_sample + invoke_dispatch_probe | degradation_probe + invoke_dispatch_probe |
| 关键 metric | route_events | feasible_nodes_full | scaling_factor | cache_savings_seconds | overall_max_cpu_util | duration_match_ratio | max_active_requests_before |
| 论文 highlight | 11 条 | 10 条 | 11 条 | 12 条 | 15 条 | 9 条 | 13 条 |
| self-check | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 |
