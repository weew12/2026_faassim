# 07_trace_oracle：faas-sim trace-driven 执行时间样例

本样例演示 **trace-driven / oracle-style** 的函数执行时间建模方式。样例从 CSV 文件读取函数执行时间轨迹，并在函数 invoke 阶段按 trace 样本控制执行时间。

## 运行方式

在项目根目录运行：

```bash
python -u examples/07_trace_oracle/main.py
python -u examples/07_trace_oracle/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 png+pdf 到 `figures/`。

## 样例目标

该样例主要回答以下问题：

1. 如何从 CSV trace 读取函数执行时间样本；
2. 如何构造一个轻量级 TraceRuntimeOracle；
3. 函数 invoke 阶段如何从 Oracle 中取样；
4. 不同函数如何使用不同执行时间轨迹；
5. 如何验证"每次 invoke 实际拿到的执行时间"和"trace 中派出的样本"完全一致。

## 拓扑

**最小 4-server 拓扑**（与 02/03/05/06 一致风格）：

```
internet ── registry_link(200Mbps) ── switch ── link_server_X(200Mbps) ── server_X (X=0..3)
                    └── DockerRegistry
```

## Trace 文件格式

样例使用 `traces/function_runtime_trace.csv`，字段：

```text
function_name, sample_id, duration
```

| 函数 | sample 数 | duration 范围 | 平均 |
|---|---|---|---|
| trace-fast-python-pi | 12 | 0.08-0.13 | 0.1017 |
| trace-slow-python-pi | 12 | 0.45-0.62 | 0.5300 |

## 实验设计

| 函数 | cpu | mem | 副本 | rps | max_requests | 期望 cursor 行为 |
|---|---|---|---|---|---|---|
| trace-fast-python-pi | 100m | 128Mi | 1 | 8 | 16 | 16 / 12 = **2 cycles**，最后停在 sample_id=4 |
| trace-slow-python-pi | 200m | 256Mi | 1 | 5 | 12 | 12 / 12 = **1 cycle**，完整一轮，不发生回卷 |

## 输出文件

运行结束后，结果会保存到 `outputs/`：

```text
# 9 个 faas-sim / oracle 内置 metric 的 CSV
trace_oracle_sample.csv             # oracle 实际派出的样本（28 行）
invocations.csv                     # 实际函数调用事件（28 行）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
invoke_dispatch_probe.csv           # invoke 派发探针（仿 02/03/05/06 模式，28 行）

# 论文 demo 关键导出
trace_input_summary.csv             # trace CSV 自身摘要
trace_sample_summary.csv            # 实际取样摘要
trace_invoke_sample_join.csv        # 论文 demo 关键：每个 invoke 与其使用的 trace sample 一一对应 + duration_match
trace_cycle_summary.csv             # trace 循环覆盖证据（fast 16 调用 / 12 样本 → cycles_used=2）
trace_invocation_summary.csv        # invocations.csv 按 function_name 聚合
trace_oracle_paper_highlight.csv    # 论文 demo 关键摘要（11 条 metric/value）
trace_oracle_self_check.csv         # 数据自检（10 项 PASS/FAIL）
```

绘图脚本生成 4 张图到 `figures/`：

```text
fig01_trace_vs_invoke_duration.png/pdf  # trace sample vs invocation t_exec 双线对比（max diff ≈ 4e-16）
fig02_sample_id_cycling.png/pdf        # trace cursor 循环覆盖（fast 1→12→1→4，slow 1→12）
fig03_per_function_duration.png/pdf    # 每个函数的 duration 分布
fig04_paper_highlight_metrics.png/pdf  # 论文 demo 关键摘要指标条形图（比例/均值/循环指标）
```

## 论文 demo 关键摘要（11 条 paper highlight）

| metric | value | note |
|---|---|---|
| trace_oracle_sample_events | 28 | trace_oracle_sample 总行数（应 == 28） |
| invocation_events | 28 | 实际函数调用事件数（应 == 28） |
| duration_match_count | 28 | trace sample_duration 与 inv t_exec 一致的行数（应 == 28） |
| duration_match_ratio | 1.0 | duration_match 比例（应 == 1.0，证明 oracle 行为正确） |
| cycles_used_fast | 2 | fast 函数 cursor 循环次数（应 == 2） |
| last_sample_id_fast | 4 | fast 函数最后一次取样的 sample_id（应 == 4，证明循环到第 4 个样本停止） |
| fast_avg_duration_s | 0.10 | fast 函数平均执行时间（应 ≈ 0.10s） |
| slow_avg_duration_s | 0.53 | slow 函数平均执行时间（应 ≈ 0.53s） |
| invoke_dispatch_probe_events | 28 | invoke_dispatch_probe 探针行数（应 == invocation_events） |
| probe_sample_match_ratio | 1.0 | invoke_dispatch_probe 与 trace_oracle_sample 的样本匹配比例 |
| probe_invocation_match_ratio | 1.0 | invoke_dispatch_probe 与 invocations 的时间/执行时长/节点匹配比例 |

## 10 项数据自检（10 / 10 PASS）

| check_id | 含义 |
|---|---|
| 01_trace_oracle_sample_is_28 | trace_oracle_sample 行数 == 28 |
| 02_invocations_is_28 | invocations 行数 == 28 |
| 03_join_rows_is_28 | trace_invoke_sample_join 行数 == 28 |
| 04_all_duration_match_true | 全部 duration_match=True（论文 demo 关键证据） |
| 05_cycles_used_fast_is_2 | cycles_used_fast == 2 |
| 06_cycles_used_slow_is_1 | cycles_used_slow == 1 |
| 07_last_sample_id_fast_is_4 | last_sample_id_fast == 4 |
| 08_fast_invocations_is_16 | fast 函数 invocations == 16 |
| 09_slow_invocations_is_12 | slow 函数 invocations == 12 |
| 10_probe_sample_invocation_consistent | probe、trace sample、invocations 三方一致 |

## 文件说明

### `main.py`

样例主入口。职责包括：

1. 创建 4-server 拓扑；
2. 初始化 Docker Registry；
3. 注册函数镜像；
4. 构造两个函数部署；
5. 配置 trace-driven 模拟器；
6. **轮询 `env.metrics.records` 直到所有 28 次 invoke 完成**（替代原 `env.timeout(2.0)` 硬等待）；
7. 导出 trace 和调用结果指标 + 论文 demo 关键摘要 + 数据自检。

### `traces/function_runtime_trace.csv`

函数执行时间轨迹文件。字段：

```text
function_name, sample_id, duration
```

### `oracle.py`

执行时间 Oracle 文件。提供：

- `TraceSample`：单条 trace 样本数据类
- `TraceRuntimeOracle`：按 function_name 维护 cursor，sample 时返回下一个样本，到末尾后循环

### `simulator.py`

函数生命周期模拟器文件。提供 `TraceOracleFunctionSimulator`：

- `deploy()` 调用 `docker.pull()`，与普通函数部署一致；
- `startup()` 固定 0.15s；
- `invoke()` 从 oracle 取样，写 `trace_oracle_sample` 探针 + `invoke_dispatch_probe` 探针，按 trace duration 执行；
- `setup()` / `teardown()` 0s。

### `analysis.py`

指标导出与分析文件。负责：

- 导出 9 个 faas-sim / oracle 内置 metric 的 CSV
- 生成 `trace_input_summary`（trace CSV 自身摘要）
- 生成 `trace_sample_summary`（实际取样摘要）
- 生成 `trace_invoke_sample_join`（论文 demo 关键：trace sample × invoke probe × invocation 三方关联）
- 生成 `trace_cycle_summary`（trace 循环覆盖证据）
- 生成 `trace_invocation_summary`（按函数聚合）
- 生成 `trace_oracle_paper_highlight`（11 条论文 demo 关键摘要）
- 生成 `trace_oracle_self_check`（10 项数据自检）

### `plot.py`

绘图脚本。读 `outputs/` CSV，输出 `figures/` 下 4 张 png+pdf：

1. **fig01_trace_vs_invoke_duration** —— trace sample_duration vs inv_t_exec 双线对比（max diff ≈ 4e-16，证明 oracle 行为正确）
2. **fig02_sample_id_cycling** —— trace cursor 循环覆盖（fast 1→12→1→4，slow 1→12）
3. **fig03_per_function_duration** —— 每个函数的 duration 分布（双子图）
4. **fig04_paper_highlight_metrics** —— 论文 demo 关键摘要条形图（只画比例、均值和循环指标，计数保留在 CSV）

### `outputs/`

CSV 输出目录。

### `figures/`

绘图输出目录（运行 plot.py 后生成）。

## 论文叙事点

> **"trace oracle 加载 24 个函数执行时间样本（12 fast + 12 slow），按 function_name 维护独立 cursor。仿真触发 28 次 invoke（16 fast + 12 slow），oracle 派出 28 个样本。`trace_invoke_sample_join` 将 trace sample、invoke_dispatch_probe 与 invocations.csv 三方对齐，duration_match、probe_sample_match、probe_invocation_match 均为 100%。fast 函数 16 次 invoke 但 trace 只有 12 个样本，cursor 循环 2 次，最后停在 sample_id=4；slow 函数 12 次 invoke 恰好覆盖一个完整 cycle，不发生回卷。"**

## 07 vs 02/03/04/05/06 demo 价值对比

| 维度 | 02_load_balancer | 03_skippy_scheduler | 04_network_flow | 05_image_pull_network | 06_resource_monitor | 07_trace_oracle |
|---|---|---|---|---|---|---|
| 仿真引擎 | faas-sim | faas-sim | Ether (纯网络流) | faas-sim + docker | faas-sim + ResourceMonitor | faas-sim + Trace Oracle |
| 拓扑 | 4-server 最小 | 4-server 最小 | 边缘→云端瓶颈 | 4-server + 1Gbps registry | 4-server 最小 | 4-server 最小 |
| 关注对象 | FunctionReplica 路由 | Pod 调度 | 网络 Flow | 镜像拉取 + 缓存 | CPU/内存利用率 | trace-driven 执行时间 |
| 数据来源 | 合成 (固定 0.3s) | 合成 (固定 0.25s) | 合成 (Flow 模型) | 合成 (固定 0.05s) | 合成 (固定 1.5s) | **CSV trace** |
| 探针 | invoke_dispatch_probe | schedule_probe + invoke_dispatch_probe | （不适用） | image_pull_probe + invoke_dispatch_probe | function_utilization + invoke_dispatch_probe | trace_oracle_sample + invoke_dispatch_probe |
| 关键 metric | route_events | feasible_nodes_full | scaling_factor | cache_savings_seconds | overall_max_cpu_util | duration_match_ratio |
| 论文 highlight | 11 条 | 10 条 | 11 条 | 12 条 | 15 条 | 11 条 |
| self-check | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 |
