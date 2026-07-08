# 13_image_cache — 节点级镜像缓存

> **目标**：通过两个对照场景验证 faas-sim 的 `docker.pull()` 与节点本地镜像缓存之间的关系，
> 量化缓存命中节省的 cold pull 耗时和网络流量，并验证 probe × flow join 一致性。

## 1. 复现步骤

```bash
# 1) 跑仿真（两个场景：same_node_cache_reuse + different_node_cold_pull）
python -u examples/13_image_cache/main.py

# 2) 跑绘图（4 张图：cache 效果对比 + per-deploy + 节点缓存状态 + 论文摘要）
python -u examples/13_image_cache/plot.py
```

输出：
- `outputs/same_node_cache_reuse/`：9 个 metric + 3 个 summary（image_cache_summary / image_cache_node_summary / probe_flow_join）
- `outputs/different_node_cold_pull/`：同上
- `outputs/` 顶层：image_cache_comparison + image_cache_paper_highlight + image_cache_self_check
- `figures/`：4 张图（png + pdf 同时输出）

## 2. 实验设计

### 2.1 跨场景对照

| 场景 | 调度 | 预期效果 |
|------|------|---------|
| `same_node_cache_reuse` | 两个函数副本都调度到 server_0 | 第二次部署命中缓存（0s） |
| `different_node_cold_pull` | 副本分别调度到 server_0 / server_1 | 两节点都首次拉取（都 5.32s） |

### 2.2 拓扑与镜像

- **2-server 最小拓扑**（与 02-12 不同的是只用 2 server，因为 13 只比较两个目标节点）：
  ```text
  DockerRegistry -- internet_link -- switch -- link_server_0 -- server_0
                                       |
                                       -- link_server_1 -- server_1
  ```
  **为什么不复用 UrbanSensingScenario**：ether.scenarios.urbansensing 在连续两次 `UrbanSensingScenario()` 调用时
  会产生不同的节点集（server_0..9 vs server_10..19），导致第二次场景的 SequenceNodeScheduler 找不到 server_0。
  13 直接用 `ether.core` 构造最小拓扑，避开这个状态污染问题。
- **共享镜像**：`image-cache-shared-cpu` (128M)，两个函数都用同一个镜像

### 2.3 SequenceNodeScheduler

`SequenceNodeScheduler` 按调度顺序返回 `target_node_names[cursor]`，然后 `cursor++`。
- `create_same_node` → `["server_0", "server_0"]` → 两个副本都到 server_0
- `create_different_node` → `["server_0", "server_1"]` → 两个副本分别到不同节点

找不到目标节点时**直接抛异常**（不再悄悄 fallback，避免 silent bug）。

### 2.4 关键探针

- `image_cache_probe`：每次 deploy 记录 `cache_hit_before` / `cache_hit_after` / `pull_duration` / `cached_image_count_before` / `cached_image_count_after`
- `invoke_dispatch_probe`：仿 02-12 模式加在 simulator.invoke 入口（13 故意不触发 invoke，但保留探针以保持与 02-12 模式对齐）
- `flow.csv`（`action_type=docker_pull`）：每次 cold pull 的网络流（`source=registry, sink=server`）

## 3. 数据自检（10 项 PASS）

```
data self-check: 10 / 10 PASS
```

| # | check_id | 含义 |
|---|---------|------|
| 01 | `same_node_cache_hit_equals_1` | same_node 场景下 cache 命中次数 == 1（第二次部署命中） |
| 02 | `same_node_cold_pull_equals_1` | same_node 场景下 cold pull 次数 == 1 |
| 03 | `same_node_flow_events_equals_1` | same_node 场景下 flow.csv 中 docker_pull 流数 == 1 |
| 04 | `different_node_cache_hit_equals_0` | different_node 场景下 cache 命中次数 == 0 |
| 05 | `different_node_cold_pull_equals_2` | different_node 场景下 cold pull 次数 == 2 |
| 06 | `different_node_flow_events_equals_2` | different_node 场景下 flow.csv 中 docker_pull 流数 == 2 |
| 07 | `different_total_equals_2x_same` | different_total_pull = 2 × same_total_pull（恒等式） |
| 08 | `speedup_ratio_equals_2` | speedup_ratio_cold_over_reuse == 2.0（**论文 demo 关键数字**） |
| 09 | `saved_bytes_equals_image_size` | saved_bytes_by_cache == 128000000（一个镜像大小） |
| 10 | `probe_flow_join_all_match_50ms` | probe × flow join 50ms 容差内全部匹配（两场景合并） |

**注意 check 11 设计**：13 故意不触发 invoke（main.py benchmark.run() 只部署不调用），
所以 `invoke_dispatch_probe` 行数 == `invocations` 行数 == 0 是预期行为。
self_check 跳过 dispatch_probe 检查，避免对"不触发 invoke"这一设计选择做误报。

## 4. 论文 demo 关键摘要（11 条）

`outputs/image_cache_paper_highlight.csv` 包含：

| metric | 期望/示例 | 含义 |
|--------|----------|------|
| `same_node_total_pull_seconds` | 5.32s | same_node 场景下总 docker.pull 耗时（含一次 cold pull） |
| `different_node_total_pull_seconds` | 10.63s | different_node 场景下总 docker.pull 耗时（含两次 cold pull） |
| `same_node_cache_hit_before_count` | 1 | same_node 场景下第二次部署的 cache 命中次数 |
| `different_node_cache_hit_before_count` | 0 | different_node 场景下 cache 命中次数（两节点均首次拉取） |
| `same_node_cold_pull_count` | 1 | same_node 场景下 cold pull 次数 |
| `different_node_cold_pull_count` | 2 | different_node 场景下 cold pull 次数 |
| `same_node_docker_pull_flow_events` | 1 | same_node 场景下 flow.csv 中 docker_pull 流数 |
| `different_node_docker_pull_flow_events` | 2 | different_node 场景下 flow.csv 中 docker_pull 流数 |
| `saved_pull_seconds_by_cache` | 5.32s | 缓存命中节省的 docker.pull 耗时 |
| `saved_bytes_by_cache` | 128MB | 缓存命中节省的网络流量 |
| `speedup_ratio_cold_over_reuse` | 2.0x | **论文 demo 一句话核心**：不同节点 vs 同节点 cold pull 耗时比 |

## 5. 4 张图说明

### fig01 — Cache Effect Comparison（论文 demo 关键图）
- 双子图：左 = total_pull_duration (s)、右 = docker_pull_bytes (MB)
- 两个柱：same_node_cache_reuse (绿) vs different_node_cold_pull (红)
- 整体标题显示 2.0x speedup
- **论文价值**：一眼看出"同节点复用缓存 vs 不同节点冷拉取"在时间和流量上的 2x 差距。

### fig02 — Per-Deploy pull_duration
- 散点图：x = deploy 序号（同一场景内），y = pull_duration (s)
- 形状：△ = cache_hit_before=False，○ = cache_hit_before=True
- 颜色：绿 = same_node、红 = different_node
- 文字标注每次部署的 duration 和 cache_hit 状态
- **论文价值**：same_node 第二次部署是绿色圆点在 0.000s（cache hit），different_node 两次都是红色三角在 5.317s（cold pull）—— 一图看出缓存机制的核心行为。

### fig03 — Node-level cached_image_count_after
- 阶梯图：x = 场景内全局 deploy 序号（start / deploy 1 / deploy 2），y = cached_image_count_after
- 三条线：same_node/server_0（绿）、different_node/server_0（红）、different_node/server_1（红）
- **论文价值**：same_node 的 server_0 在 deploy 1 后已有缓存，deploy 2 继续复用；different_node 的 server_0 和 server_1 分别在各自首次部署后缓存 1 张独立镜像（互不共享）。

### fig04 — Paper Highlight Metrics
- 论文 demo 关键摘要指标的横向条形图（11 个 metric）
- **论文价值**：saved_bytes_by_cache 128MB 是最显眼的 bar，量化了缓存带来的网络流量节省。

## 6. 与 02-12 的 demo 价值对比

| 维度 | 02 LB | 05 scale | 06 trig | 08 deg | 11 fault | 12 cold | **13 image_cache** |
|------|-------|---------|---------|--------|---------|---------|--------------------|
| 验证目标 | 路由均衡 | 副本伸缩 | 请求生成 | 性能退化 | 故障判定 | 冷启动路径 | **节点镜像缓存** |
| 探针 | dispatch_probe | dispatch_probe | dispatch_probe | dispatch_probe | dispatch + fault | dispatch + phase | **dispatch + cache_probe** |
| 关键 join | route×probe×inv | — | — | probe×degradation | probe×fault×inv | probe×inv（按 phase） | **probe×flow×docker_pull** |
| 核心数字 | balance_std=0 | scale_min→max | rps=profile | slowdown_pct | failure_rate=0.23 | first/warm=3.75x | **cache speedup=2.0x** |
| 论文 chart | 阶梯图 | 副本数曲线 | 到达曲线 | 窗口阴影散点 | Gantt + 对比柱状图 | Gantt | **双柱 + 散点 + 阶梯** |

**13 的独特价值**：13 是 02-12 中**唯一一个**通过"双场景对照"验证缓存机制的样例。
其他样例关注"单一现象如何发生"，13 关注"两个对照场景下，同一现象如何不同"。
13 还能进一步扩展到"集群级镜像缓存策略"（如预热策略、跨节点缓存共享），为论文中的"边缘 Serverless 镜像分发"提供基础。

## 7. 输出文件清单

```
examples/13_image_cache/
├── main.py                                # 双场景 + SequenceNodeScheduler + 跨场景对比
├── scheduler.py                           # SequenceNodeScheduler（按预设顺序选节点）
├── simulator.py                           # ImageCacheFunctionSimulator + invoke_dispatch_probe
├── analysis.py                            # 9 metrics + scenario summary + cross-scenario + paper_highlight + self_check
├── plot.py                                # 4 张图（png + pdf）
├── README.md                              # 本文件
├── outputs/
│   ├── same_node_cache_reuse/             # 场景 1
│   │   ├── image_cache_probe.csv          # 2 次 deploy 的 cache_hit_before / pull_duration
│   │   ├── image_cache_summary.csv        # 场景摘要
│   │   ├── image_cache_node_summary.csv   # 按节点聚合
│   │   ├── probe_flow_join.csv            # probe × docker_pull flow 关联
│   │   ├── flow.csv                       # faas-sim 网络流
│   │   ├── schedule.csv                   # faas-sim 内置
│   │   ├── function_deployments.csv       # faas-sim 内置
│   │   ├── function_replicas.csv          # faas-sim 内置
│   │   ├── replica_deployment.csv         # faas-sim 内置
│   │   ├── invocations.csv                # 0 行（13 不触发 invoke）
│   │   └── invoke_dispatch_probe.csv      # 0 行（保留探针占位）
│   ├── different_node_cold_pull/          # 场景 2（结构同场景 1）
│   ├── image_cache_comparison.csv         # 跨场景 side-by-side
│   ├── image_cache_paper_highlight.csv    # 论文 demo 关键摘要
│   └── image_cache_self_check.csv         # 10 项数据自检
└── figures/
    ├── fig01_cache_effect_comparison.png/pdf
    ├── fig02_per_deploy_pull_duration.png/pdf
    ├── fig03_node_cache_state_evolution.png/pdf
    └── fig04_paper_highlight_metrics.png/pdf
```

## 8. 设计取舍

- **双场景而非单场景**：13 故意构造两个对照场景（same_node / different_node），让论文 demo 能"对比"而非"展示单一现象"。
  这比 11 个单场景样例更直接地证明缓存机制的行为差异。
- **2-server 拓扑而非 4-server**：13 只需要两个目标节点做对比，用 2-server 最小拓扑让 SequenceNodeScheduler
  行为可预测。如果用 4-server 拓扑，调度器可能要回退到其他 server，破坏 same_node_cache_reuse 的"两次都到 server_0"语义。
- **直接抛异常而非 fallback**：SequenceNodeScheduler 找不到目标节点时**直接抛 RuntimeError**，
  不再悄悄 fallback 到其他节点。silent fallback 是最难排查的 bug 类型，抛异常至少让结果可解释。
- **故意不触发 invoke**：13 关注 deploy 阶段的镜像拉取差异，invoke 阶段不受缓存影响（warm 0.05s），
  触发 invoke 不会让 demo 更清晰，反而会让数据自检多 1 个无关 check。
  invoke_dispatch_probe 仍然在 simulator 入口（仿 02-12 模式），方便其他场景复用 simulator。
- **恒等式而非绝对值**：self_check 故意不检查 `saved_pull_seconds ≈ 5.32s` 的具体值（受 docker.pull 实际拉取时间影响），
  改用 `different_total_pull == 2 × same_total_pull` 这种**两场景之间的相对关系**作为不变量，
  这是拓扑无关的、可跨多次运行保持稳定的恒等式。
