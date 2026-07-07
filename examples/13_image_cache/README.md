# 13_image_cache：faas-sim 节点级镜像缓存样例

本样例用于演示 faas-sim 中节点级镜像缓存机制，重点展示 `docker.pull()`、`node_state.docker_images` 和 `flow.csv` 中 `docker_pull` 网络流之间的关系。

## 运行方式

将 `image_cache/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/13_image_cache/main.py
```

## 样例目标

该样例主要回答以下问题：

1. `docker.pull()` 如何检查节点本地镜像缓存；
2. 同一节点重复部署相同镜像时为什么第二次拉取耗时接近 0；
3. 不同节点首次部署相同镜像时为什么仍然需要各自拉取；
4. 镜像缓存命中如何影响 `flow.csv` 中的 `docker_pull` 网络流数量；
5. **如何验证 probe 记录的 pull_duration 和 flow.csv 中的 docker_pull 时长一致**（论文 demo 关键证据）。

## 实验设计

样例构造一个**最小拓扑**（避开 ether.scenarios.urbansensing 的状态污染问题）：

```text
DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0
                                     |
                                     -- link_server_1 -- server_1
```

> **拓扑选择说明**：原版本复用 UrbanSensingScenario，但 ether.scenarios.urbansensing 在
> 连续两次 `UrbanSensingScenario()` 调用时会**产生不同的节点集**（server_0..9 vs server_10..19），
> 导致 SequenceNodeScheduler 在第二次场景里找不到 server_0，退回到 server_10，
> 两个场景的 cache 行为完全一样。这里用 ether.core 直接构造最小拓扑，确保两个场景都用同一份拓扑。

样例运行两个场景：

```text
same_node_cache_reuse       两个函数都调度到 server_0（第二次命中缓存）
different_node_cold_pull    两个函数分别调度到 server_0 和 server_1（各拉一次）
```

两个函数都使用同一个镜像：

```text
image-cache-shared-cpu   128M
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/13_image_cache/outputs/
```

每个场景有独立子目录：

```text
outputs/same_node_cache_reuse/        # 同节点缓存复用
outputs/different_node_cold_pull/     # 不同节点各拉一次
```

每个子目录：

```text
image_cache_probe.csv       # 每次部署的 cache_hit_before / pull_duration / cached_image_count_after
image_cache_summary.csv     # 单场景摘要
image_cache_node_summary.csv # 按 (scenario, node_name, image) 分组
probe_flow_join.csv         # 论文 demo 关键：probe × docker_pull flow 关联验证
flow.csv                    # 网络流（action_type=docker_pull）
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv             # 设计上为 0 行（本样例不触发请求）
```

跨场景对比文件（在 `outputs/` 顶层）：

```text
image_cache_comparison.csv     # 两场景 side-by-side
image_cache_paper_highlight.csv # 论文 demo 关键摘要：saved_pull_seconds + saved_bytes + speedup_ratio
```

## 关键导出与图

### 1. `image_cache_paper_highlight.csv` —— 论文 demo 核心

```text
metric                              value
same_node_total_pull_seconds       5.317
different_node_total_pull_seconds  10.635
same_node_cold_pull_count          1.0
different_node_cold_pull_count     2.0
saved_pull_seconds_by_cache        5.317      ← 缓存节省的时间
saved_bytes_by_cache               128000000  ← 缓存节省的网络流量（128M）
speedup_ratio_cold_over_reuse      2.0        ← 论文 demo 一句话核心
```

**关键发现**：节点级镜像缓存让 cold pull 时间**减半**（10.6s → 5.3s），网络流量也减半（256MB → 128MB）。

### 2. `image_cache_comparison.csv` —— 两场景 side-by-side

```text
              scenario  deploy_events  cache_hit_before_count  cold_pull_count  total_pull_duration  docker_pull_flow_events  docker_pull_total_bytes
same_node_cache_reuse              2                       1                1             5.317                            1                128000000
different_node_cold_pull           2                       0                2            10.635                            2                256000000
```

### 3. `probe_flow_join.csv` —— probe × docker_pull flow 关联（论文 demo 关键证据）

按 (scenario, function, image, node_name) 关联 probe 和 flow.csv：

| cache_hit_before | probe_pull_duration | flow_duration | flow_bytes | duration_match_50ms |
|---|---|---|---|---|
| False | 5.32s | 5.32s | 128MB | True |
| True | 0s | (空) | (空) | True（cache hit 不应产生 flow） |

预期 2 行 × 2 场景 = 4 行，**`duration_match_50ms` 全部 True**。

### 4. 论文 demo 关键图 —— 节点缓存效果对比

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("examples/13_image_cache/outputs/image_cache_comparison.csv")
fig, ax = plt.subplots(figsize=(8, 4))
x = range(len(df))
width = 0.35
ax.bar([i - width/2 for i in x], df["total_pull_duration"], width,
       label="total_pull_duration", color="steelblue")
ax.bar([i + width/2 for i in x], df["docker_pull_total_bytes"] / 1e6, width,
       label="docker_pull_total_bytes (MB)", color="darkorange")
ax.set_xticks(list(x))
ax.set_xticklabels(df["scenario"], rotation=10, ha="right")
ax.set_ylabel("value")
ax.set_title("Image cache effect: same_node vs different_node")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
plt.tight_layout()
plt.show()
```

## 数据自洽验证

跑完 `main.py` 后，6 个核心不变量应同时满足：

| 不变量 | 验证方式 |
|---|---|
| `same_node_cache_reuse` 的 `cache_hit_before_count == 1` | summary |
| `same_node_cache_reuse` 的 `cold_pull_count == 1` | summary |
| `same_node_cache_reuse` 的 `docker_pull_flow_events == 1` | summary |
| `different_node_cold_pull` 的 `cache_hit_before_count == 0` | summary |
| `different_node_cold_pull` 的 `cold_pull_count == 2` | summary |
| `different_node_cold_pull` 的 `docker_pull_flow_events == 2` | summary |
| `probe_flow_join.csv` 的 `duration_match_50ms` 全部 True | 直接读 |
| `image_cache_paper_highlight.csv` 的 `speedup_ratio_cold_over_reuse == 2.0` | 直接读 |

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 构造**最小拓扑**（避开 ether.scenarios.urbansensing 状态污染）；
2. 初始化 Docker Registry；
3. 注册共享镜像；
4. 运行同节点缓存复用场景；
5. 运行不同节点冷拉取场景；
6. 导出场景结果和跨场景对比摘要；
7. log paper highlight（cache 节省时间）。

### `scheduler.py`

序列固定节点调度器文件。

该文件提供：

```text
SequenceNodeScheduler
```

按预设顺序把两个函数副本调度到同一节点或不同节点。`schedule()` 时如果找不到目标节点，**直接抛异常**（不再悄悄 fallback 到其他节点，避免 silent bug）。

### `simulator.py`

镜像缓存观测模拟器文件。

该文件提供：

```text
ImageCacheSimulatorFactory
ImageCacheFunctionSimulator
```

其核心逻辑是在 `deploy()` 阶段调用 `docker.pull()` 前后检查节点镜像缓存状态，并记录 `image_cache_probe` 指标。

### `analysis.py`

指标导出与分析文件。

该文件负责导出：

- 8 个 faas-sim / cache 原生 metric（`image_cache_probe` / `flow` /
  `schedule` / `function_deployments` / `function_deployment_lifecycle` /
  `function_replicas` / `replica_deployment` / `invocations`）
- `image_cache_summary.csv`：单场景摘要
- `image_cache_node_summary.csv`：按节点聚合
- `probe_flow_join.csv`：probe × docker_pull flow 关联
- `image_cache_comparison.csv`：两场景对比
- `image_cache_paper_highlight.csv`：论文 demo 关键摘要

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。