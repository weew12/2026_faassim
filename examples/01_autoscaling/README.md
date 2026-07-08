# 01_autoscaling：faas-sim 原生自动伸缩样例

本样例用于演示 faas-sim 的原生自动伸缩能力，重点展示函数部署、持续请求负载、自动扩容触发、按仿真时间对齐的副本数量时间线、probe×invocation 关联验证、论文 demo 关键摘要和数据自洽检查。

## 运行方式

在项目根目录运行：

```bash
python -u examples/01_autoscaling/main.py
```

`main.py` 会固定随机种子 `20260707`，输出可复现。运行结束后会生成 CSV，并打印 12 个 self-check。

生成论文 demo 图：

```bash
python -u examples/01_autoscaling/plot.py
```

默认写入 `examples/01_autoscaling/outputs/plots/`：

- `autoscaling_rps_vs_replicas.png` + `.pdf`：双 y 轴 RPS vs Replicas 时间线，论文 demo 最核心的图。
- `autoscaling_rps_histogram.png` + `.pdf`：RPS 分布直方图，验证负载围绕 40 RPS 波动。
- `autoscaling_replicas_timeline.png` + `.pdf`：副本数阶梯图，标记扩容时刻。
- `autoscaling_paper_highlight.png` + `.pdf`：关键指标条形图。

## 样例目标

1. 演示 `ScalingConfiguration` 中 `scale_min`、`scale_max`、`alert_window`、`target_average_rps` 的配置方式。
2. 演示如何启用 `DefaultFaasSystem(scale_by_average_requests=True)`。
3. 使用 40 RPS 指数到达负载触发自动扩容。
4. 导出 faas-sim 原始指标，包括 `scale`、`schedule`、`replica_deployment`、`invocations`。
5. 额外导出 `autoscaling_scale_probe.csv`，用 `env.now` 记录扩容事件，解决原始 `scale.csv` 的 wall clock time 不能和 `invocations.t_start` 直接对齐的问题。
6. 生成 `autoscaling_rps_replicas_timeline.csv`，作为论文图的数据源。
7. 做 probe×invocation 关联验证，证明 simulator 派发的 `t_exec=0.2s` 与 faas-sim 实际 `invocations.t_exec` 一致。

## 输出文件

运行结束后，结果保存到：

```text
examples/01_autoscaling/outputs/
```

主要文件：

```text
scale.csv                                # faas-sim 原始 scale 事件，time 是 wall clock
schedule.csv                             # faas-sim 调度事件
function_deployment.csv                  # faas-sim 函数部署记录
replica_deployment.csv                   # faas-sim 副本部署/启动/setup/finish 记录
invocations.csv                          # faas-sim 调用记录，t_start 是 simtime
flow.csv                                 # faas-sim 网络流
autoscaling_invoke_probe.csv             # simulator 派发 invoke 前记录的 probe
autoscaling_scale_probe.csv              # 示例新增：按 simtime 记录 scale_up/scale_down
autoscaling_rps_replicas_timeline.csv    # 1s 窗口聚合 RPS 与 replicas
autoscaling_probe_invocation_join.csv    # probe × invocations 关联结果
autoscaling_summary.csv                  # 自动伸缩摘要
autoscaling_paper_highlight.csv          # 论文 demo 关键指标
```

## 关键输出

### autoscaling_scale_probe.csv

该文件是本样例最重要的修正点。它按仿真时间记录副本数变化：

| simtime | delta | requested_delta | replicas_before | replicas | action |
|---:|---:|---:|---:|---:|---|
| 0.0 | 1 | 1 | 0 | 1 | scale_up |
| 4.0 | 7 | 8 | 1 | 8 | scale_up |

含义：初始部署 1 个副本；负载开始后，平均请求伸缩器在 `t=4s` 将副本数扩到 `scale_max=8`。

### autoscaling_rps_replicas_timeline.csv

该文件用于画 RPS vs Replicas 时间线：

| simtime | window | invocation_count | rps | replicas |
|---:|---:|---:|---:|---:|
| 0.0 | 1.0 | 0 | 0.0 | 1 |
| 1.0 | 1.0 | 0 | 0.0 | 1 |
| 2.0 | 1.0 | 0 | 0.0 | 1 |
| 3.0 | 1.0 | 36 | 36.0 | 1 |
| 4.0 | 1.0 | 37 | 37.0 | 8 |
| 5.0 | 1.0 | 29 | 29.0 | 8 |

这张表能正确展示“负载出现后，副本数从 1 扩到 8”，而不是从 `t=0` 就显示 8 个副本。

### autoscaling_paper_highlight.csv

固定随机种子后，当前关键指标为：

| metric | value |
|---|---:|
| scale_events | 2 |
| scale_up_events | 2 |
| scale_down_events | 0 |
| max_replicas | 8 |
| min_replicas | 1 |
| invocation_events | 2000 |
| total_simtime | 53.5918 |
| avg_exec_time | 0.2000 |
| avg_rps_overall | 37.3191 |
| scale_up_factor | 8.0000 |
| peak_rps | 53.0000 |
| peak_rps_simtime | 14.0000 |
| final_replicas | 8 |
| first_reach_max_replicas_simtime | 4.0000 |
| first_load_window_simtime | 3.0000 |
| scale_up_response_time | 1.0000 |
| probe_invocation_t_exec_match | 1.0000 |
| probe_invocation_simtime_match | 1.0000 |

### autoscaling_probe_invocation_join.csv

按 `(function_name, replica_id, simtime)` 关联 `autoscaling_invoke_probe.csv` 和 `invocations.csv`，验证：

- `probe_t_exec == inv_t_exec`
- `probe_simtime == inv_t_start`

预期 2000 行，`t_exec_match` 与 `simtime_match` 全部为 True。

## 数据自洽检查

当前 `main.py` 运行后应输出：

```text
PASS invocation_events_count : invocations=2000, expected=2000
PASS max_replicas_ge_min_replicas : max=8, min=1
PASS scale_up_events_ge_1 : scale_up_events=2
PASS rps_replicas_timeline_non_zero_windows : non-zero windows=51
PASS timeline_min_replicas_matches_summary : timeline_min=1, summary_min=1
PASS timeline_max_replicas_matches_summary : timeline_max=8, summary_max=8
PASS probe_invocation_t_exec_match : t_exec_match=2000/2000
PASS probe_invocation_simtime_match : simtime_match=2000/2000
PASS paper_highlight_avg_rps
PASS paper_highlight_max_replicas
PASS paper_highlight_scale_up_factor
PASS paper_highlight_probe_invocation_t_exec_match
=== 12 passed, 0 failed ===
```

## 论文 demo 一段话总结

在 40 RPS 持续负载下，faas-sim 原生平均请求自动伸缩器触发扩容，副本数从 `scale_min=1` 扩到 `scale_max=8`，扩容倍数为 8x。固定随机种子 `20260707` 时，样例共完成 2000 次调用，平均 RPS 为 37.32，峰值 RPS 为 53，首次负载窗口在 `t=3s`，副本数在 `t=4s` 达到 8，因此可报告 1 秒窗口粒度下的扩容响应时间约为 1 秒。probe×invocation join 显示 simulator 派发的 `t_exec=0.2s` 与 faas-sim 记录的 `invocations.t_exec` 100% 一致。

## 文件说明

- `main.py`：样例主入口，创建拓扑、部署函数、生成负载、固定随机种子并导出结果。
- `system.py`：创建启用原生 autoscaling 的 FaaS system，并额外记录 `autoscaling_scale_probe`。
- `simulator.py`：函数生命周期与调用执行模拟器，调用耗时固定为 0.2s。
- `analysis.py`：导出 CSV、构建 RPS/Replicas 时间线、生成摘要、自洽检查。
- `plot.py`：读取输出 CSV 并生成 4 张 PNG/PDF 图。
- `outputs/`：运行结果目录。
