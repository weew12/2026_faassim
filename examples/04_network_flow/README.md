# 04_network_flow：Ether 原生网络流样例

本样例演示 faas-sim 底层 Ether 网络流仿真能力，重点展示网络拓扑、路由、链路带宽、RTT、单流传输和多流共享瓶颈链路。它不走 FaaS 函数部署流程，而是直接使用 `ether.core.Flow`，适合作为网络层能力的独立 demo。

## 运行方式

在项目根目录运行：

```bash
python -u examples/04_network_flow/main.py
python -u examples/04_network_flow/plot.py
```

第一步产出 CSV 到 `outputs/`，第二步产出 PNG/PDF 到 `figures/`。

## 样例目标

1. 演示如何创建 Ether 网络节点、链路和连接。
2. 演示为什么计算节点之间需要通过 `Link` 或透明节点连接。
3. 演示如何查询 `Route`，并导出 path、hops、RTT 和 bottleneck link。
4. 演示 `Flow` 如何根据路由链路带宽推进仿真时间。
5. 用同大小 flow 对比单流和三流并发，展示共享瓶颈链路的公平带宽分配。
6. 导出论文 demo 关键摘要、自检结果和图表。

## 拓扑

边缘到云端的共享瓶颈拓扑：

```text
edge_client_a -- access_a(100 Mbps) -- edge_switch -- bottleneck(10 Mbps) -- core_switch -- cloud_access(80 Mbps) -- cloud_server
edge_client_b -- access_b(100 Mbps) --/
edge_client_c -- access_c(100 Mbps) --/
```

| 链路 | 带宽 | 作用 |
|---|---:|---|
| access_a / access_b / access_c | 100 Mbps | 边缘接入链路 |
| bottleneck | 10 Mbps | 共享瓶颈链路 |
| cloud_access | 80 Mbps | 云端接入链路 |

三条 edge 到 cloud 的路由都经过同一条 `bottleneck` 链路，因此并发传输会触发带宽共享。

## 场景

| 场景 | flow 数 | 每条 flow 大小 | 启动时间 |
|---|---:|---:|---|
| single_flow | 1 | 30M | 0.0s |
| concurrent_bottleneck | 3 | 30M | 0.0s / 0.0s / 0.0s |

单流和并发流使用同样的 30M 数据大小，因此 `scaling_factor = concurrent_avg_duration / single_duration` 可以公平表示三条流共享瓶颈后的延迟放大。

## 输出文件

运行结束后，结果保存到 `examples/04_network_flow/outputs/`：

```text
network_flow.csv                    # 每次网络流传输的原始记录，4 行
network_route.csv                   # 三条 edge -> cloud 静态路由
network_flow_performance.csv        # 每个 flow 的吞吐、耗时、RTT、瓶颈链路
network_flow_summary.csv            # 按 scenario 聚合的吞吐/耗时/scaling_factor
network_bottleneck_summary.csv      # 按 bottleneck 链路聚合的统计
network_flow_paper_highlight.csv    # 论文 demo 关键指标
network_flow_self_check.csv         # 10 项 self-check
```

绘图输出到 `examples/04_network_flow/figures/`：

```text
fig01_throughput_per_flow.png/pdf
fig02_duration_per_flow.png/pdf
fig03_scaling_factor.png/pdf
fig04_paper_highlight_metrics.png/pdf
```

## 关键结果

### Per-Flow Performance

| scenario | flow_id | duration | throughput_mbps | bottleneck_fraction_of_link |
|---|---|---:|---:|---:|
| single_flow | single_a_to_cloud | 24.8623 | 9.6532 | 0.9653 |
| concurrent_bottleneck | flow_a | 74.3468 | 3.2281 | 0.3228 |
| concurrent_bottleneck | flow_b | 74.3468 | 3.2281 | 0.3228 |
| concurrent_bottleneck | flow_c | 74.3468 | 3.2281 | 0.3228 |

单流吞吐接近 10 Mbps 瓶颈上限；三条并发流各自接近 `10 / 3 = 3.33 Mbps` 的公平份额。

### Paper Highlight

| metric | value |
|---|---:|
| single_flow_throughput_mbps | 9.6532 |
| single_flow_duration_s | 24.8623 |
| concurrent_flow_count | 3 |
| concurrent_flow_throughput_mbps | 3.2281 |
| concurrent_flow_duration_s | 74.3468 |
| scaling_factor | 2.9903 |
| bottleneck_bandwidth_mbps | 10.0 |
| bottleneck_share_per_flow_mbps | 3.3333 |
| fair_share_utilization_ratio | 0.9684 |
| concurrent_throughput_std | 0.0 |
| all_flows_share_bottleneck | True |

`fair_share_utilization_ratio` 表示并发场景下实际单流吞吐与理想公平份额的比值，越接近 1，越接近理想公平共享。

## Self-Check

`main.py` 运行后应输出 `data self-check: 10 / 10 PASS`：

| check_id | 含义 |
|---|---|
| 01_single_flow_count_is_1 | single_flow 有 1 条流 |
| 02_concurrent_flow_count_is_3 | concurrent_bottleneck 有 3 条流 |
| 03_single_throughput_near_bottleneck | 单流吞吐接近 10 Mbps |
| 04_concurrent_throughput_near_share | 并发单流吞吐接近公平份额 |
| 05_scaling_factor_near_3 | 三条同大小流共享瓶颈，延迟放大约 3 倍 |
| 06_all_flows_share_one_bottleneck | 所有 flow 共享同一瓶颈链路 |
| 07_single_total_bytes_is_30M | 单流总字节数为 30M |
| 08_concurrent_total_bytes_is_90M | 并发总字节数为 90M |
| 09_rtt_consistent_across_flows | 所有 flow 的 RTT 一致 |
| 10_summary_paper_scaling_consistent | summary 与 paper highlight 的 scaling_factor 一致 |

## 图表说明

- `fig01_throughput_per_flow`：展示单流接近 10 Mbps，三条并发流接近 3.33 Mbps 公平份额。
- `fig02_duration_per_flow`：展示同样 30M 数据，三流并发耗时约为单流 3 倍。
- `fig03_scaling_factor`：直接展示 `1.00x` vs `2.99x`。
- `fig04_paper_highlight_metrics`：汇总论文 demo 关键数值，跳过布尔指标。

## 文件说明

- `main.py`：样例入口，构建拓扑、收集路由、运行单流/并发场景并导出结果。
- `topology.py`：构造共享瓶颈拓扑。
- `flow_runner.py`：直接使用 `ether.core.Flow` 执行传输并记录结构化结果。
- `analysis.py`：生成性能表、摘要、paper highlight 和 self-check。
- `plot.py`：读取 CSV，生成 4 张论文 demo 图。

## 论文叙事点

三条同大小 30M flow 共享 10 Mbps bottleneck 时，单流吞吐从 9.65 Mbps 降到 3.23 Mbps，接近理想公平份额 3.33 Mbps；平均传输耗时从 24.86s 增加到 74.35s，延迟放大 2.99x。该结果说明 Ether Flow 能正确反映共享瓶颈链路下的带宽竞争与公平共享。
