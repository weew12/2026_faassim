# 05_image_pull_network：faas-sim 镜像拉取网络样例

本样例用于演示 faas-sim 中 `docker.pull()` 与网络传输之间的关系，重点展示首次镜像拉取、同节点镜像缓存复用以及镜像大小对拉取耗时的影响。

## 运行方式

将 `05_image_pull_network/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/05_image_pull_network/main.py
```

## 样例目标

该样例主要回答以下问题：

1. `docker.pull()` 如何触发网络 Flow；
2. `flow.csv` 中的 `action_type=docker_pull` 表示什么；
3. 同一节点第一次部署某个镜像时为什么需要拉取；
4. 同一节点再次部署相同镜像时为什么可以复用缓存；
5. 镜像大小如何影响镜像拉取耗时；
6. 如何导出镜像拉取耗时和网络传输结果。

## 实验设计

样例依次部署三个函数：

```text
image-pull-small-cold   使用 small 镜像，首次部署，触发 docker_pull
image-pull-small-warm   使用同一个 small 镜像，同节点部署，复用镜像缓存
image-pull-large-cold   使用 large 镜像，首次部署，触发更大的 docker_pull
```

为了稳定观察缓存复用，样例使用 `FixedNodeScheduler` 将函数副本固定部署到同一节点。

### 拓扑与瓶颈链路

本样例用 `UrbanSensingScenario` 生成拓扑：
- 3 个城区的 `SharedLinkCell(shared_bandwidth=500 Mbps)`，每个内含若干感知节点 + `IoTComputeBox`；
- 1 个 `Cloudlet(5, 2)`，上联 `FiberToExchange(1000 Mbps)`；
- `FixedNodeScheduler` 把 pod 优先放在 `server_0`，**`server_0` 位于 cloudlet 内部**。

所以 `docker.pull` 的端到端路径是：

```text
DockerRegistry → internet → cloudlet downlink(1 Gbps) → switch → switch_lan_11 → link_server_0(1 Gbps) → server_0
```

**端到端瓶颈 = 1 Gbps cloudlet 上联**（不是 25 Mbps MobileConnection）。
`pull_speed_mb_per_sec` 实测 ~120 MB/s，对应 1 Gbps × 0.97 / 8 = **121.25 MB/s**，理论与仿真一致。

> 提示：若想让 `server_0` 走 neighborhood 的 25 Mbps MobileConnection 链路，需把 `server_0` 放到 `SharedLinkCell` 内（不是 cloudlet）。

## 输出文件

运行结束后，结果会保存到：

```text
examples/05_image_pull_network/outputs/
```

主要包括：

```text
image_pull_probe.csv                   # 每次 deploy 阶段的镜像拉取耗时原始记录
image_pull_summary.csv                 # 按 function × image × node 分组的拉取摘要
image_pull_cold_warm_comparison.csv    # 按 image × cold/warm 分类 + cache_savings_seconds
image_pull_size_duration_comparison.csv # 论文 demo 关键图：image_size vs pull_duration
image_pull_deploy_phase_duration.csv   # 论文 demo 关键图：3 个 pod 的 deploy 阶段总耗时
flow.csv                               # 全部网络流记录，action_type=docker_pull 等
image_pull_flow_summary.csv            # 按 action_type × source × sink 分组的流摘要
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv                        # main.py 末尾对 small-cold 触发 10 个请求的调用记录
```

### 论文 demo 关键图说明

**1. `image_pull_size_duration_comparison.csv`** —— 镜像大小 vs 拉取耗时散点图

列：`function_name / image / node_name / image_size_mb / pull_duration_seconds / pull_speed_mb_per_sec`

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/05_image_pull_network/outputs/image_pull_size_duration_comparison.csv")
# 排除 warm cache hit 的数据点（duration=0）
cold_df = df[df.pull_duration_seconds > 0]
fig, ax = plt.subplots(figsize=(8, 4))
ax.scatter(cold_df.image_size_mb, cold_df.pull_duration_seconds, s=100, c="steelblue")
for _, row in cold_df.iterrows():
    ax.annotate(row["image"], (row["image_size_mb"], row["pull_duration_seconds"]))
ax.set_xlabel("image size (MB)"); ax.set_ylabel("pull duration (s)")
ax.set_title("Image pull duration vs image size")
ax.grid(True, alpha=0.3)
plt.show()
```

**2. `image_pull_deploy_phase_duration.csv`** —— 3 个 pod 的 deploy 阶段总耗时对比

列：`function_name / image / node_name / image_pull_duration / startup_simtime / setup_simtime / deploy_to_finish_simtime`

> 单位是 simtime（仿真秒），不是 wall clock。
> `deploy_to_finish_simtime = image_pull_duration + startup_simtime + setup_simtime`，
> 其中 `startup_simtime=0.1, setup_simtime=0` 来自 `simulator.py`。

```python
df = pd.read_csv("examples/05_image_pull_network/outputs/image_pull_deploy_phase_duration.csv")
df.set_index("function_name")["deploy_to_finish_simtime"].plot.bar(figsize=(8, 4))
plt.ylabel("deploy-to-finish (simtime seconds)")
plt.title("Pod deploy phase duration (simtime)")
plt.xticks(rotation=20, ha="right")
plt.tight_layout(); plt.show()
```

**3. `image_pull_cold_warm_comparison.csv`** —— 含 cache_savings 字段

`cache_savings_seconds` 字段：cold_pull - warm_cache_hit 的差值，**论文里最直观的"缓存节省"指标**。

```python
df = pd.read_csv("examples/05_image_pull_network/outputs/image_pull_cold_warm_comparison.csv")
print(df[["image", "cold_or_warm", "cache_savings_seconds", "cache_savings_ratio"]])
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册 small / large 函数镜像；
4. 顺序部署三个函数；
5. 固定调度到同一节点；
6. 运行仿真；
7. 导出镜像拉取和网络流指标。

### `scheduler.py`

固定节点调度器文件。

该文件提供：

```text
FixedNodeScheduler
```

它优先选择 `server_0`，用于保证多个函数副本部署到同一节点，从而稳定观察节点镜像缓存复用。

### `simulator.py`

镜像拉取观测模拟器文件。

该文件提供：

```text
ImagePullSimulatorFactory
ImagePullFunctionSimulator
```

其核心逻辑是在 `deploy()` 中调用 `docker.pull()`，并记录 `image_pull_probe` 指标。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `image_pull_probe`、`flow`、`schedule`、`replica_deployment` 等指标，并生成摘要结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
