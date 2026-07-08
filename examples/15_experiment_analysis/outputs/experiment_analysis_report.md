# experiment_analysis 实验结果分析报告

## 1. 输入信息

- source_name：`batch_experiment_outputs`
- input_dir：`D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs`
- run_count：`8`

## 2. Run-level 结果预览

```text
run_id,run_dir,case_id,policy,workload,seed,rps,max_requests,scheduled_node,probe_events,probe_avg_duration,probe_min_duration,probe_max_duration,probe_p95_duration,invocation_events,invocation_avg_duration,invocation_min_duration,invocation_max_duration,invocation_p95_duration,function_count,schedule_events,scheduled_node_count,scheduled_nodes,schedule_success_rate,flow_events,flow_total_bytes,flow_total_duration,flow_avg_duration,replica_deployment_events,replica_node_count
default_skippy__low_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\default_skippy__low_load__seed_1,default_skippy__low_load__seed_1,default_skippy,low_load,1,3,12,server_1,12,0.21851082224417187,0.1822677981217605,0.2477946989549786,0.2472812791022146,12,0.21851082224417184,0.1822677981217602,0.2477946989549786,0.2472812791022146,1,6,1,server_1,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
default_skippy__low_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\default_skippy__low_load__seed_2,default_skippy__low_load__seed_2,default_skippy,low_load,2,3,12,server_1,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,1,6,1,server_1,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
default_skippy__medium_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\default_skippy__medium_load__seed_1,default_skippy__medium_load__seed_1,default_skippy,medium_load,1,8,24,server_1,24,0.21900399596851172,0.1801684842680888,0.2556216556443137,0.2546792725602765,24,0.21900399596851164,0.1801684842680888,0.2556216556443136,0.2546792725602764,1,6,1,server_1,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
default_skippy__medium_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\default_skippy__medium_load__seed_2,default_skippy__medium_load__seed_2,default_skippy,medium_load,2,8,24,server_1,24,0.2204746078892134,0.1821955885672655,0.2595855650359794,0.25640307616558783,24,0.2204746078892134,0.1821955885672657,0.2595855650359793,0.2564030761655878,1,6,1,server_1,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
fixed_node__low_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\fixed_node__low_load__seed_1,fixed_node__low_load__seed_1,fixed_node,low_load,1,3,12,server_0,12,0.21851082224417187,0.1822677981217605,0.2477946989549786,0.2472812791022146,12,0.21851082224417184,0.1822677981217602,0.2477946989549786,0.2472812791022146,1,6,1,server_0,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
fixed_node__low_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\fixed_node__low_load__seed_2,fixed_node__low_load__seed_2,fixed_node,low_load,2,3,12,server_0,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,1,6,1,server_0,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
fixed_node__medium_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\fixed_node__medium_load__seed_1,fixed_node__medium_load__seed_1,fixed_node,medium_load,1,8,24,server_0,24,0.21900399596851172,0.1801684842680888,0.2556216556443137,0.2546792725602765,24,0.21900399596851164,0.1801684842680888,0.2556216556443136,0.2546792725602764,1,6,1,server_0,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
fixed_node__medium_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\fixed_node__medium_load__seed_2,fixed_node__medium_load__seed_2,fixed_node,medium_load,2,8,24,server_0,24,0.2204746078892134,0.1821955885672655,0.2595855650359794,0.25640307616558783,24,0.2204746078892134,0.1821955885672657,0.2595855650359793,0.2564030761655878,1,6,1,server_0,1.0,1,48000000,2.0183814432989693,2.0183814432989693,8,1
```

## 3. Policy / Workload 聚合摘要

```text
policy,workload,runs,avg_probe_events,avg_invocation_events,mean_probe_avg_duration,mean_probe_p95_duration,mean_invocation_avg_duration,mean_invocation_p95_duration,mean_flow_total_bytes,mean_scheduled_node_count
default_skippy,low_load,2,12.0,12.0,0.2210785899045785,0.25170146116041947,0.22107858990457846,0.25170146116041947,48000000.0,1.0
default_skippy,medium_load,2,24.0,24.0,0.21973930192886254,0.25554117436293217,0.2197393019288625,0.2555411743629321,48000000.0,1.0
fixed_node,low_load,2,12.0,12.0,0.2210785899045785,0.25170146116041947,0.22107858990457846,0.25170146116041947,48000000.0,1.0
fixed_node,medium_load,2,24.0,24.0,0.21973930192886254,0.25554117436293217,0.2197393019288625,0.2555411743629321,48000000.0,1.0
```

## 4. 策略对比结果（其他 policy vs default_skippy 基线）

```text
workload,baseline_policy,policy,mean_probe_avg_duration_baseline,mean_probe_avg_duration_current,mean_probe_avg_duration_delta,mean_probe_avg_duration_relative,mean_probe_p95_duration_baseline,mean_probe_p95_duration_current,mean_probe_p95_duration_delta,mean_probe_p95_duration_relative,mean_invocation_avg_duration_baseline,mean_invocation_avg_duration_current,mean_invocation_avg_duration_delta,mean_invocation_avg_duration_relative,mean_invocation_p95_duration_baseline,mean_invocation_p95_duration_current,mean_invocation_p95_duration_delta,mean_invocation_p95_duration_relative,mean_flow_total_bytes_baseline,mean_flow_total_bytes_current,mean_flow_total_bytes_delta,mean_flow_total_bytes_relative
low_load,default_skippy,fixed_node,0.2210785899045785,0.2210785899045785,0.0,0.0,0.25170146116041947,0.25170146116041947,0.0,0.0,0.22107858990457846,0.22107858990457846,0.0,0.0,0.25170146116041947,0.25170146116041947,0.0,0.0,48000000.0,48000000.0,0.0,0.0
medium_load,default_skippy,fixed_node,0.21973930192886254,0.21973930192886254,0.0,0.0,0.25554117436293217,0.25554117436293217,0.0,0.0,0.2197393019288625,0.2197393019288625,0.0,0.0,0.2555411743629321,0.2555411743629321,0.0,0.0,48000000.0,48000000.0,0.0,0.0
```

## 5. 论文 demo 关键摘要

```text
metric,value,note
total_runs,8,分析的 run 总数（每个 case 一行）
total_policies,2,策略数（聚合维度）
total_workloads,2,负载数（聚合维度）
total_seeds,2,随机种子数
total_invocations,144,跨所有 run 的总 invoke 次数
total_probes,144,跨所有 run 的总 probe 次数（应 == total_invocations）
comparison_row_count,2,experiment_policy_comparison.csv 的行数（baseline 自身被跳过，应 == (policies-1) × workloads）
scheduled_nodes__default_skippy,server_1,default_skippy 策略实际选过的节点集合（聚合自 4 个 run）
high_capacity_hit_ratio__default_skippy,1.0,default_skippy 策略选中 server_1 的比例（应 = 1.0，表示 capacity-aware 策略全部选中 server_1）
scheduled_nodes__fixed_node,server_0,fixed_node 策略实际选过的节点集合（聚合自 4 个 run）
high_capacity_hit_ratio__fixed_node,0.0,fixed_node 策略选中 server_1 的比例（应 = 0.0，表示 fixed_node 策略不会选中 server_1）
default_skippy__avg_probe_seconds__low_load,0.2210785899045785,default_skippy 策略在 low_load 下的 mean_probe_avg_duration（sim 模型诚实特性：capacity 不改 single-invoke duration）
default_skippy__avg_probe_seconds__medium_load,0.21973930192886254,default_skippy 策略在 medium_load 下的 mean_probe_avg_duration（sim 模型诚实特性：capacity 不改 single-invoke duration）
fixed_node__avg_probe_seconds__low_load,0.2210785899045785,fixed_node 策略在 low_load 下的 mean_probe_avg_duration（sim 模型诚实特性：capacity 不改 single-invoke duration）
fixed_node__avg_probe_seconds__medium_load,0.21973930192886254,fixed_node 策略在 medium_load 下的 mean_probe_avg_duration（sim 模型诚实特性：capacity 不改 single-invoke duration）
speedup_ratio_fixed_over_default_skippy__low_load,1.0,在 low_load 下，fixed_node / default_skippy 的 probe_avg_duration 比值（应 = 1.0，sim 诚实特性）
speedup_ratio_fixed_over_default_skippy__medium_load,1.0,在 medium_load 下，fixed_node / default_skippy 的 probe_avg_duration 比值（应 = 1.0，sim 诚实特性）
fixed_node_vs_default_skippy__probe_avg_duration_relative__low_load,0.0,fixed_node 相对 default_skippy baseline 的 probe_avg_duration 相对变化（应 = 0.0，sim 诚实特性）
fixed_node_vs_default_skippy__probe_avg_duration_relative__medium_load,0.0,fixed_node 相对 default_skippy baseline 的 probe_avg_duration 相对变化（应 = 0.0，sim 诚实特性）
```

## 6. 说明

本报告由 `examples/15_experiment_analysis/main.py` 自动生成。默认情况下，脚本优先读取 `examples/14_batch_experiment/outputs/`，如果该目录不存在，则读取本样例自带的 `sample_results/`。
