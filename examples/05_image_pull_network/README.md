# 05_image_pull_network：faas-sim 镜像拉取网络样例

本样例演示 faas-sim 中 `docker.pull()` 与网络传输之间的关系，重点展示**首次镜像拉取、同节点镜像缓存复用以及镜像大小对拉取耗时的影响**。

## 运行方式

在项目根目录运行：

```bash
python -u examples/05_image_pull_network/main.py
python -u examples/05_image_pull_network/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 png+pdf 到 `figures/`。

## 样例目标

该样例主要回答以下问题：

1. `docker.pull()` 如何触发网络 Flow；
2. `flow.csv` 中的 `action_type=docker_pull` 表示什么；
3. 同一节点第一次部署某个镜像时为什么需要拉取；
4. 同一节点再次部署相同镜像时为什么可以复用缓存；
5. 镜像大小如何影响镜像拉取耗时；
6. 如何导出镜像拉取耗时 + 网络传输 + 论文 demo 关键摘要 + 数据自检。

## 拓扑

**最小 4-server 拓扑**（与 02/03 一致风格，避开 UrbanSensingScenario 状态污染）：

```
internet ── registry_link(1000Mbps) ── switch ── link_server_X(1000Mbps) ── server_X (X=0..3)
                    └── DockerRegistry (init_docker_registry)
```

| 链路 | 带宽 (Mbps) | 作用 |
|---|---|---|
| registry_link | **1000** | **保留原版 1Gbps cloudlet 上联数字**（pull_speed ≈ 121 MB/s） |
| link_server_X | 1000 | 服务器接入链路 |

## 实验设计

样例依次部署三个函数，**FixedNodeScheduler 强制全部调度到 server_0**：

| 顺序 | 函数 | 镜像 | 副本 | cache 状态 | 拉取耗时 |
|---|---|---|---|---|---|
| 1 | image-pull-small-cold | small (32M) | 1 | cold | ~0.30s |
| 2 | image-pull-small-warm | small (32M) | 1 | **warm (cache hit)** | ~0s |
| 3 | image-pull-large-cold | large (192M) | 1 | cold | ~1.62s |

最后对 small-cold 触发 10 个请求（rps=10），让 `invocations.csv` 也有数据。

## 输出文件

运行结束后，结果会保存到 `outputs/`：

```text
# 9 个 faas-sim 内置 metric 的 CSV
image_pull_probe.csv                    # 每次 deploy 阶段的镜像拉取耗时原始记录（3 行）
flow.csv                                # 全部网络流（action_type=docker_pull）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv                         # small-cold 触发 10 个请求的调用记录
invoke_dispatch_probe.csv               # invoke 派发探针（仿 02/03 模式）

# 论文 demo 关键导出
image_pull_summary.csv                  # 按 function × image × node 分组
image_pull_flow_summary.csv             # 按 action_type × source × sink 分组
image_pull_cold_warm_comparison.csv     # 含 cache_savings_seconds / cache_savings_ratio
image_pull_size_duration_comparison.csv # 论文 demo 关键图：image_size vs pull_duration
image_pull_deploy_phase_duration.csv    # 论文 demo 关键图：3 个 pod 的 deploy 阶段总耗时
image_pull_paper_highlight.csv          # 论文 demo 关键摘要（12 条 metric/value）
image_pull_self_check.csv               # 数据自检（10 项 PASS/FAIL）
```

绘图脚本生成 4 张图到 `figures/`：

```text
fig01_size_vs_duration_scatter.png/pdf  # 镜像大小 vs 拉取耗时散点图（含 121MB/s 理论参考线）
fig02_deploy_phase_duration.png/pdf     # 3 个 pod 的 deploy 阶段总耗时
fig03_cold_warm_comparison.png/pdf      # cold vs warm cache 节省时间柱状图
fig04_paper_highlight_metrics.png/pdf   # 论文 demo 关键摘要指标条形图
```

## 论文 demo 关键摘要（12 条 paper highlight）

| metric | value | note |
|---|---|---|
| small_image_size_mb | 32.0 | small 镜像大小（MB） |
| large_image_size_mb | 192.0 | large 镜像大小（MB） |
| small_cold_pull_duration_s | 0.302918 | small 镜像冷拉取耗时（秒），首次部署 32M 镜像 |
| small_warm_cache_hit_duration_s | 0.000000 | small 镜像 cache 命中耗时（秒），同节点复用 |
| large_cold_pull_duration_s | 1.622505 | large 镜像冷拉取耗时（秒），首次部署 192M 镜像 |
| small_cold_pull_speed_mb_per_sec | 105.6393 | small 冷拉取速度（MB/s），应接近 121 MB/s（1Gbps/8×0.97） |
| large_cold_pull_speed_mb_per_sec | 118.3355 | large 冷拉取速度（MB/s），应接近 121 MB/s |
| **cache_savings_seconds** | **0.302918** | **small 缓存命中节省时间（秒），论文 demo 关键数字** |
| cache_savings_ratio | 1.000000 | small 缓存节省比例（warm/cold），越接近 1 缓存越有效 |
| docker_pull_flow_count | 2 | docker_pull 网络流数量（small-cold + large-cold = 2，warm 不算） |
| bandwidth_utilization_ratio | 0.9236 | 实测拉取速度 / 理论最大速度（链路利用率） |
| invocation_events | 10 | invoke 调用事件数（small-cold 触发 10 个请求） |

## 10 项数据自检（10 / 10 PASS）

| check_id | 含义 |
|---|---|
| 01_total_pulls_is_3 | 总镜像拉取次数 == 3（cold + warm + cold） |
| 02_small_cold_pull_positive | small 冷拉取耗时 > 0 |
| 03_small_warm_is_cache_hit | small warm 耗时 ≤ 1e-9（cache hit） |
| 04_large_cold_longer_than_small_cold | large 冷拉取 > small 冷拉取 |
| 05_cache_savings_seconds_close_to_cold | cache_savings_seconds ≈ small_cold_pull_duration |
| 06_cache_savings_ratio_near_one | cache_savings_ratio ≈ 1.0 |
| 07_invocations_count_is_10 | invoke 调用事件数 == 10 |
| 08_docker_pull_flow_count_is_2 | docker_pull 流数 == 2 |
| 09_paper_docker_pull_flow_count_is_2 | paper_highlight docker_pull_flow_count == 2 |
| 10_probe_invocation_consistent | probe 行数 + invocations 数一致 |

## 文件说明

### `main.py`

样例主入口。职责包括：

1. 创建 4-server 拓扑；
2. 初始化 Docker Registry；
3. 注册 small / large 函数镜像；
4. 顺序部署三个函数；
5. 固定调度到同一节点（FixedNodeScheduler）；
6. 运行仿真；
7. 导出镜像拉取和网络流指标 + 论文 demo 关键摘要 + 数据自检。

### `scheduler.py`

固定节点调度器文件。提供 `FixedNodeScheduler`，优先选择 `server_0`，用于保证多个函数副本部署到同一节点，从而稳定观察节点镜像缓存复用。

### `simulator.py`

镜像拉取观测模拟器文件。提供 `ImagePullFunctionSimulator`：

- `deploy()` 调用 `docker.pull()`，记录 `image_pull_probe`（含 image_pull_duration + cache_hit_like）
- `invoke()` 写 `invoke_dispatch_probe`（仿 02/03 模式）
- `startup()` 固定 0.1s，`setup()` 0s，`invoke()` 0.05s

### `analysis.py`

指标导出与分析文件。负责：

- 导出 9 个 faas-sim 内置 metric 的 CSV
- 生成 `image_pull_summary` / `image_pull_flow_summary`
- 生成 `image_pull_cold_warm_comparison`（含 cache_savings_seconds / cache_savings_ratio）
- 生成 `image_pull_size_duration_comparison`（含 pull_speed_mb_per_sec）
- 生成 `image_pull_deploy_phase_duration`（含 deploy_to_finish_simtime）
- 生成 `image_pull_paper_highlight`（12 条论文 demo 关键摘要）
- 生成 `image_pull_self_check`（10 项数据自检）

### `plot.py`

绘图脚本。读 `outputs/` CSV，输出 `figures/` 下 4 张 png+pdf：

1. **fig01_size_vs_duration_scatter** —— 镜像大小 vs 拉取耗时（含 121MB/s 理论参考线）
2. **fig02_deploy_phase_duration** —— 3 个 pod 的 deploy 阶段总耗时（标注 pull/cache hit）
3. **fig03_cold_warm_comparison** —— cold vs warm 缓存节省时间
4. **fig04_paper_highlight_metrics** —— 论文 demo 关键摘要条形图

### `outputs/`

CSV 输出目录。

### `figures/`

绘图输出目录（运行 plot.py 后生成）。

## 论文叙事点

> **"32M 小镜像在 1Gbps 链路上冷拉取仅需 0.30s（≈106 MB/s，链路利用率 92%）；同节点复用同一镜像时 docker.pull 直接命中缓存，耗时降至 0s（节省 0.30s）。192M 大镜像冷拉取需要 1.62s（≈118 MB/s），证明 docker.pull 端到端耗时与镜像大小严格线性相关。"**

## 05 vs 02/03/04 demo 价值对比

| 维度 | 02_load_balancer | 03_skippy_scheduler | 04_network_flow | 05_image_pull_network |
|---|---|---|---|---|
| 仿真引擎 | faas-sim | faas-sim | Ether (纯网络流) | faas-sim + docker |
| 拓扑 | 4-server 最小 | 4-server 最小 | 边缘→云端瓶颈 | 4-server + 1Gbps registry |
| 关注对象 | FunctionReplica 路由 | Pod 调度 | 网络 Flow | 镜像拉取 + 缓存 |
| 调度 | Skippy 默认 | Skippy 默认 | (无) | FixedNodeScheduler(server_0) |
| 探针 | invoke_dispatch_probe | schedule_probe + invoke_dispatch_probe | （不适用） | image_pull_probe + invoke_dispatch_probe |
| 关键 metric | route_events | feasible_nodes_full | scaling_factor | cache_savings_seconds |
| 论文 highlight | 11 条 | 10 条 | 11 条 | 12 条 |
| self-check | 10 项 | 10 项 | 10 项 | 10 项 |