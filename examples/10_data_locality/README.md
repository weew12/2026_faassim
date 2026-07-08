# 10_data_locality：faas-sim 数据本地性样例

本样例演示 faas-sim / Skippy 中的**数据本地性机制**，重点展示 `StorageIndex`、函数数据标签、`DataLocalityPriority` 和 `simulate_data_download()` 之间的关系。

## 运行方式

在项目根目录运行：

```bash
python -u examples/10_data_locality/main.py
python -u examples/10_data_locality/plot.py
```

第一步产出 CSV 到 `outputs/`（两个场景子目录 + 顶层对比文件），第二步产出 png+pdf 到 `figures/`。

## 样例目标

该样例主要回答以下问题：

1. 如何使用 `StorageIndex` 登记对象数据所在节点；
2. 函数如何通过标签声明需要读取哪个对象；
3. Skippy 默认 `DataLocalityPriority` 如何影响节点选择；
4. `simulate_data_download()` 如何根据数据位置触发网络传输；
5. 数据本地性感知调度和强制远端调度在下载耗时上的差异。

## 拓扑

**自定义边缘-存储拓扑**（4 节点 + 1 存储节点）：

```
                         storage_near
                              |
                        storage_link (200Mbps)
                              |
edge_near -- near_link -- data_switch -- mid_link -- edge_mid
(200Mbps,                    (10ms)
 3ms latency)                   |
                              far_link (10Mbps, 30ms latency)
                              |
                           edge_far

internet -- internet_link -- data_switch  (DockerRegistry 自动接入)
```

| 节点 | 标签 | 到 storage_near 带宽 | 延迟 |
|---|---|---|---|
| edge_near | zone=near | 200Mbps | 3ms |
| edge_mid | zone=mid | 60Mbps | 10ms |
| edge_far | zone=far | 10Mbps | 30ms |
| storage_near | data.skippy.io/storage=true | （存储节点本身） | - |

## 实验设计

| 场景 | 调度器 | 选中节点 | 数据下载耗时 |
|---|---|---|---|
| data_locality_aware | InstrumentedDataLocalityScheduler | **edge_near**（默认 Skippy DataLocality） | ~2.65s |
| forced_remote | ForcedNodeScheduler | **edge_far**（强制） | ~52.88s |

**输入对象**：`video-bucket/frame-seq-001` (64MB)，位于 `storage_near`。

**函数声明数据标签**：
- `data.skippy.io/receives-from-storage=64M`
- `data.skippy.io/receives-from-storage/path=video-bucket/frame-seq-001`

> **本样例不触发 invoke**：Benchmark 只调用 `poll_available_replica`，关注**数据下载阶段**的耗时差异，不涉及函数执行业务。`invocations.csv` 永远是 0 行（符合设计）。

## 输出文件

运行结束后，结果会保存到 `outputs/`（两个场景子目录 + 顶层对比文件）：

```text
outputs/data_locality_aware/        # 数据本地性感知场景
├── data_locality_scheduler_result.csv  # 调度器记录：feasible_nodes / needed_images / selected_node
├── data_locality_candidate.csv         # 每个候选节点的估算下载时间 + 带宽
├── data_locality_download.csv          # 实际下载时长（每个 replica 一条）
├── candidate_vs_actual_join.csv        # 论文 demo 关键：candidate 估算 vs download 实际
├── data_locality_summary.csv           # 单场景摘要（含 theoretical_download_duration 反算）
├── flow.csv / network.csv / schedule.csv / etc.

outputs/forced_remote/              # 强制远端调度对比场景（同样结构，但无 candidate）

# 跨场景对比文件（顶层）
outputs/data_locality_comparison.csv        # 两场景 side-by-side
outputs/data_locality_paper_highlight.csv   # 论文 demo 关键摘要（11 条 metric/value，含 note 列）
outputs/data_locality_self_check.csv         # 数据自检（10 项 PASS/FAIL）
```

绘图脚本生成 4 张图到 `figures/`：

```text
fig01_aware_vs_forced_comparison.png/pdf  # aware vs forced 下载耗时柱状图（含 19.9× speedup 标题）
fig02_candidate_estimates.png/pdf         # edge_near/mid/far 估算下载时间柱状图（含实际叠加）
fig03_download_timeline.png/pdf          # simtime vs download_duration 时序图（阶梯图）
fig04_paper_highlight_metrics.png/pdf     # 论文 demo 关键摘要指标条形图
```

## 论文 demo 关键摘要（11 条 paper highlight）

| metric | value | note |
|---|---|---|
| aware_download_seconds | 2.6542 | data_locality_aware 场景的实际下载耗时（edge_near） |
| forced_download_seconds | 52.8795 | forced_remote 场景的实际下载耗时（edge_far） |
| **speedup_ratio_forced_over_aware** | **19.9231** | **forced / aware 的延迟放大倍数（论文 demo 关键数字）** |
| aware_selected_node | edge_near | data_locality_aware 场景 Skippy 默认调度选择的节点 |
| forced_selected_node | edge_far | forced_remote 场景 ForcedNodeScheduler 强制选择的节点 |
| aware_theoretical_seconds | 2.56 | aware 场景理论下载时间（按 near_link=200Mbps 反算） |
| forced_theoretical_seconds | 51.2 | forced 场景理论下载时间（按 far_link=10Mbps 反算） |
| aware_actual_vs_theoretical_diff | 0.0942 | aware 场景实际 - 理论下载时间（越小越好） |
| forced_actual_vs_theoretical_diff | 1.6795 | forced 场景实际 - 理论下载时间 |
| edge_near_match_tolerance_5pct | True | edge_near 行的 Skippy 估算 vs 实际下载误差 < 5% |
| data_size_bytes | 64000000 | 输入对象 video-bucket/frame-seq-001 大小（64M） |

## 10 项数据自检（10 / 10 PASS）

| check_id | 含义 |
|---|---|
| 01_speedup_ratio_above_10 | forced / aware >= 10× |
| 02_aware_selected_edge_near | data_locality_aware 选 edge_near |
| 03_forced_selected_edge_far | forced_remote 选 edge_far |
| 04_edge_near_match_tolerance_5pct | edge_near 行 Skippy 估算 vs 实际 < 5% 误差 |
| 05_aware_diff_less_than_1s | aware 场景 实际 - 理论 < 1s |
| 06_forced_diff_less_than_10s | forced 场景 实际 - 理论 < 10s |
| 07_invocations_count_is_zero | invocations.csv == 0 行（设计上不触发 invoke） |
| 08_candidate_join_rows_at_least_1 | candidate_vs_actual_join 行数 >= 1 |
| 09_paper_summary_consistent | paper_highlight 数字与 summary 一致 |
| 10_paper_speedup_matches_comparison | paper_highlight speedup 与 comparison 一致 |

## 文件说明

### `main.py`

样例主入口。职责包括：

1. 创建数据本地性拓扑；
2. 创建 StorageIndex；
3. 注册函数镜像；
4. 构造带数据标签的函数部署；
5. 分别运行数据_locality_aware 和 forced_remote 两个场景；
6. 导出结果、生成对比摘要 + paper_highlight + data_self_check；
7. log 论文 demo 关键摘要（`speedup = forced / aware`）。

### `topology.py`

拓扑构建文件。创建 `edge_near` / `edge_mid` / `edge_far` / `storage_near` 4 个节点，并设置不同带宽和延迟，用于稳定制造近数据节点与远数据节点的差异。

### `storage.py`

对象存储索引文件。提供：

- `DEFAULT_DATA_OBJECT`：video-bucket/frame-seq-001 (64M) on storage_near
- `build_storage_index()`：构造 StorageIndex 并 put DataItem

### `scheduler.py`

调度器文件。提供：

- `InstrumentedDataLocalityScheduler`：保留 Skippy 默认调度语义，并记录每个候选节点的 `estimated_download_time` 和 `best_bandwidth_mbps`
- `ForcedNodeScheduler`：强制调度到指定节点（用于对比组）

### `simulator.py`

函数生命周期模拟器文件。提供 `DataLocalityFunctionSimulator`：

- `deploy()` 调用 `docker.pull()`，与普通函数部署一致；
- `startup()` 固定 0.15s；
- `setup()` 调用 `simulate_data_download(env, replica)` 并写 `data_locality_download` 探针（含 t_start/t_end/simtime）；
- `invoke()` 0.1s（设计触发但实际不会运行）；
- `setup()` / `teardown()` 0s。

### `analysis.py`

指标导出与分析文件。负责：

- 导出 10 个 faas-sim / 探针内置 metric 的 CSV
- 生成 `candidate_vs_actual_join`（probe × download join）
- 生成 `data_locality_summary`（单场景摘要 + theoretical_download_duration 反算）
- 生成 `data_locality_comparison`（两场景 side-by-side）
- 生成 `data_locality_paper_highlight`（11 条论文 demo 关键摘要，含 note 列）
- 生成 `data_locality_self_check`（10 项数据自检）

### `plot.py`

绘图脚本。读 `outputs/` CSV，输出 `figures/` 下 4 张 png+pdf：

1. **fig01_aware_vs_forced_comparison** —— 两个场景下载耗时对比（论文 demo 关键图，含 19.9× speedup 标题）
2. **fig02_candidate_estimates** —— 候选节点估算下载时间（含实际叠加）
3. **fig03_download_timeline** —— simtime vs download_duration 阶梯图（论文 demo 关键图）
4. **fig04_paper_highlight_metrics** —— 论文 demo 关键摘要条形图

### `outputs/`

CSV 输出目录（两个场景子目录 + 顶层对比文件）。

### `figures/`

绘图输出目录（运行 plot.py 后生成）。

## 论文叙事点

> **"Skippy 默认 DataLocalityPriority 选择 edge_near（200Mbps, 3ms），实际下载 2.65s；强制调度到 edge_far（10Mbps, 30ms）需要 52.88s；speedup = 19.92×。edge_near 行的 Skippy 估算（2.56s）与实际 simulate_data_download()（2.65s）误差 < 5%。理论下载时间由 near_link=200Mbps 与 far_link=10Mbps 反算（2.56s / 51.2s），与实际差值 < 0.10s / 1.68s，证明 faas-sim 网络模型与数据本地性估算口径一致。"**

## 10 vs 02-09 demo 价值对比

| 维度 | 02_load_balancer | 03_skippy_scheduler | 04_network_flow | 05_image_pull_network | 06_resource_monitor | 07_trace_oracle | 08_degradation | 09_topologies | 10_data_locality |
|---|---|---|---|---|---|---|---|---|---|
| 仿真引擎 | faas-sim | faa-sim | Ether | faas-sim + docker | faas-sim + ResourceMonitor | faas-sim + Trace Oracle | faas-sim + Degradation Model | faas-sim Topology 静态分析 | **faas-sim + Storage + DataLocality** |
| 拓扑 | 4-server 最小 | 4-server 最小 | 边缘→云端瓶颈 | 4-server + 1Gbps | 4-server 最小 | 4-server 最小 | 4-server 最小 | 4 种代表性拓扑对比 | **边缘-存储 4 节点** |
| 关注对象 | FunctionReplica 路由 | Pod 调度 | 网络 Flow | 镜像拉取 + 缓存 | CPU/内存利用率 | trace-driven 执行时间 | 节点竞争退化 | 拓扑规模 + 路由特征 | **数据本地性 + 下载延迟** |
| 是否跑仿真 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗（静态） | **✓** |
| 是否触发 invoke | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | **✗（设计上）** |
| 探针 | invoke_dispatch_probe | schedule_probe + invoke_dispatch_probe | （不适用） | image_pull_probe + invoke_dispatch_probe | function_utilization + invoke_dispatch_probe | trace_oracle_sample + invoke_dispatch_probe | degradation_probe + invoke_dispatch_probe | （不适用） | **data_locality_download（含 simtime）** |
| 关键 metric | route_events | feasible_nodes_full | scaling_factor | cache_savings_seconds | overall_max_cpu_util | duration_match_ratio | max_active_requests_before | total_graph_nodes | **speedup_ratio_forced_over_aware** |
| 论文 highlight | 11 条 | 10 条 | 11 条 | 12 条 | 15 条 | 9 条 | 13 条 | 14 条 | **11 条** |
| self-check | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | 10 项 | **10 项** |
