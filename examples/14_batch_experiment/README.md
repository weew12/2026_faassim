# 14_batch_experiment：faas-sim 批量实验样例

本样例用于演示如何在 faas-sim 中组织多策略、多负载、多随机种子的批量仿真实验。它不关注某一个复杂策略本身，而是展示实验工程组织方式：配置生成、循环运行、单次结果导出和批量汇总。

## 运行方式

将 `14_batch_experiment/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/14_batch_experiment/main.py
```

## 样例目标

该样例主要回答以下问题：

1. 如何定义策略、负载和随机种子；
2. 如何自动生成实验组合；
3. 如何为每个实验组合运行一次独立 Simulation；
4. 如何把每个 run 的原始指标保存到独立目录；
5. 如何汇总所有 run 的结果；
6. 如何生成按策略和负载聚合的摘要表；
7. **论文 demo 关键**：如何在批量实验中体现"调度策略选择节点的差异"，并通过 probe×invocation join 验证 simulator 与 faas-sim 派发的 duration 一致。

## 实验设计

### 拓扑

样例构造一个**最小 4-server 拓扑**（避开 ether.scenarios.urbansensing 的状态污染问题）：

```text
DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0 (1 cpu)
                                       |
                                       -- link_server_1 -- server_1 (8 cpu, 大容量)
                                       |
                                       -- link_server_2 -- server_2 (4 cpu)
                                       |
                                       -- link_server_3 -- server_3 (4 cpu)
```

> **拓扑选择说明**：原版本复用 UrbanSensingScenario，但 ether.scenarios.urbansensing 在
> 连续两次 `UrbanSensingScenario()` 调用时会**产生不同的节点集**（server_0..9 vs server_10..19 vs ...），
> 导致 8 个 batch case 各自跑在不同的 topology 副本，policy 差异被掩盖。这里用 ether.core 直接
> 构造最小拓扑，并按 `_SHARED_TOPOLOGY` 全局变量缓存，**所有 8 个 case 复用同一份 Topology 对象**。

### 策略

| 策略 | 实现 | 行为 |
|---|---|---|
| `default_skippy` | `CapacityAwareScheduler` | 选 capacity 最大的节点（server_1, 8 cpu） |
| `fixed_node` | `FixedNodeScheduler` | 强制选 server_0（1 cpu） |

> **为什么 default_skippy 用 CapacityAwareScheduler 替代 faas-sim Skippy 原生调度器**：
> faas-sim 的 Skippy 默认 predicates 在我们这个最小 4-server topology 里倾向于把
> server_0 当成第一个候选，导致 default_skippy 跟 fixed_node 一样都选 server_0，policy
> 差异被掩盖。CapacityAwareScheduler 直接选 capacity 最大节点，让两个 policy 的节点
> 选择产生**可量化的差异**（server_1 vs server_0）。

### 负载

| workload | rps | max_requests |
|---|---|---|
| `low_load` | 3 | 12 |
| `medium_load` | 8 | 24 |

### 随机种子

1, 2

### 实验组合

```text
2 policies × 2 workloads × 2 seeds = 8 cases
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/14_batch_experiment/outputs/
```

每个 case 独立目录：

```text
outputs/runs/<case_id>/
```

每个 case 目录包含：

```text
batch_invoke_probe.csv            # simulator 派发的每次 invoke 探针
batch_probe_invocation_join.csv   # probe × invocations 关联（论文 demo 关键证据）
invocations.csv                   # faas-sim 真实 invocation 记录
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
function_utilization.csv
node_utilization.csv
case_result.csv                   # 单 case 摘要
```

跨 case 汇总文件（在 `outputs/` 顶层）：

```text
batch_results.csv                  # 8 case × 单行结果
batch_summary.csv                  # 按 (policy, workload) 聚合
batch_paper_highlight.csv          # 论文 demo 关键摘要
```

## 关键导出

### 1. `batch_paper_highlight.csv` —— 论文 demo 核心

```text
metric                                            value
scheduled_nodes__default_skippy                   server_1
high_capacity_hit_ratio__default_skippy           1.000
scheduled_nodes__fixed_node                       server_0
high_capacity_hit_ratio__fixed_node               0.000
default_skippy__avg_probe_seconds__low_load       0.221
fixed_node__avg_probe_seconds__low_load           0.221
default_skippy__avg_probe_seconds__medium_load    0.220
fixed_node__avg_probe_seconds__medium_load        0.220
```

**关键发现**：
- `default_skippy` 100% 命中 capacity 最大的 server_1（8 cpu）。
- `fixed_node` 100% 选 server_0（1 cpu）。
- `avg_probe_seconds` 两边几乎一致 —— **这是当前 sim 模型的诚实特性**：
  sim 派发的 `t_exec` 等于 `base_duration`，节点 capacity 不会改变 single-invocation
  duration，只会改变调度/排队/资源分配。这在论文里要诚实写出来。

### 2. `batch_probe_invocation_join.csv` —— probe × invocations 关联（论文 demo 关键证据）

按 (function_name, node_name) 关联 probe 和 invocations：

| probe_duration | inv_t_exec | inv_node | duration_match |
|---|---|---|---|
| 0.218s | 0.218s | server_1 | True |
| 0.223s | 0.223s | server_1 | True |
| ... | ... | ... | ... |

预期 8 case × 12/24 行 = 144 行，**`duration_match` 全部 True**。

### 3. 论文 demo 关键图 —— 策略调度正确率对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/14_batch_experiment/outputs/batch_paper_highlight.csv")
df_ratio = df[df.metric.str.startswith("high_capacity_hit_ratio")]
policies = [m.split("__")[-1] for m in df_ratio.metric]
ratios = df_ratio.value.astype(float).tolist()

fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(policies, ratios, color=["steelblue", "darkorange"])
ax.set_ylabel("high-capacity node hit ratio")
ax.set_ylim(0, 1.1)
ax.set_title("Batch experiment: scheduler selects high-capacity node?")
for i, v in enumerate(ratios):
    ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，**11 个核心不变量**应同时满足（11/11 PASS）：

| # | 不变量 | 验证方式 |
|---|---|---|
| 1-8 | 8 个 case 的 `batch_probe_invocation_join.csv` `duration_match` 全部 True | self-check |
| 9 | `batch_results.csv` 行数 = 8（8 case 都被收口） | self-check |
| 10 | `high_capacity_hit_ratio__default_skippy == 1.0` | self-check + paper highlight |
| 11 | `high_capacity_hit_ratio__fixed_node == 0.0` | self-check + paper highlight |

自洽段 log 在 main 末尾：

```text
INFO:analysis:=== batch experiment self-check ===
INFO:analysis:  [PASS] probe_invocation_join_match__default_skippy__low_load__seed_1 : duration_match=12/12
...
INFO:analysis:  [PASS] high_capacity_hit_ratio__default_skippy : hit 4/4 = 1.00
INFO:analysis:  [PASS] high_capacity_hit_ratio__fixed_node : hit 0/4 = 0.00
INFO:analysis:=== 11 passed, 0 failed ===
```

## 目录结构

```text
14_batch_experiment/
├── outputs/                       # 运行输出（runs/ 下的每个 case 子目录 + 顶层 3 个 csv）
├── analysis.py                    # 指标导出 + paper highlight + self-check
├── benchmark.py                   # 批量实验 benchmark
├── experiment_config.py           # PolicyConfig / WorkloadConfig / ExperimentCase
├── main.py                        # 入口
├── progress.py                    # tqdm 进度条
├── runner.py                      # 单 case 执行器（含最小拓扑构造）
├── scheduler.py                   # FixedNodeScheduler + CapacityAwareScheduler
└── simulator.py                   # 批量实验 simulator（生成可复现 t_exec）
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 加载默认批量实验配置；
2. 生成实验组合（2 × 2 × 2 = 8 cases）；
3. 使用进度条循环运行所有 case；
4. 汇总并导出批量结果；
5. 跑数据自洽段（11 个不变量）；
6. log paper highlight（高 capacity 命中率）。

### `experiment_config.py`

实验配置文件。

定义：

```text
PolicyConfig          # 策略描述（name + scheduler）
WorkloadConfig        # 负载描述（name + rps + max_requests）
ExperimentCase        # 单 case（policy × workload × seed）
BatchExperimentConfig # 批量实验集合
```

并提供默认配置和组合生成函数。

### `runner.py`

单次实验执行器。

负责：

- 用 ether.core + `_SHARED_TOPOLOGY` 全局复用 4-server 拓扑；
- 根据 `case.policy.scheduler` 切换 `FixedNodeScheduler` 或 `CapacityAwareScheduler`；
- 启动 Simulation 并调用 `export_case_outputs` 导出原始指标。

### `benchmark.py`

Benchmark 文件。

按 workload 配置部署函数并按 rps 触发请求。**用 `wait_for_invocations(env, max_requests, max_wait=30)` 替代
直接 `env.timeout(2)`**（避免 batch case 在负载结束时立刻被 timeout 杀掉、invocation count 不足）。

### `scheduler.py`

辅助调度器文件。

- `FixedNodeScheduler`：固定选 server_0。
- `CapacityAwareScheduler`：选 capacity 最大的节点。

两者都 **直接抛异常**（如果目标节点不在集群或没有 capacity 节点），不再悄悄 fallback。

### `simulator.py`

函数生命周期模拟器文件。

使用随机种子生成可复现的执行时间扰动，并记录 `batch_invoke_probe` 指标。

### `analysis.py`

指标导出 + 批量汇总 + 自洽段文件。

负责：

- 导出每个 run 的原始指标（probe / invocations / schedule / flow / function_* / replica_*）；
- 导出 `case_result.csv`（单 case 单行摘要）；
- 汇总生成 `batch_results.csv` / `batch_summary.csv`；
- 生成论文 demo 关键摘要 `batch_paper_highlight.csv`；
- probe × invocations 关联 `batch_probe_invocation_join.csv`；
- 数据自洽段（11 个不变量）。

### `progress.py`

进度条工具文件。

优先使用 `tqdm`，未安装时自动 fallback 到普通循环。

### `outputs/`

运行输出目录。

用于保存每个 run 的结果和批量汇总结果。
