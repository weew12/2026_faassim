# experiment_analysis 实验结果分析报告

## 1. 输入信息

- source_name：`batch_experiment_outputs`
- input_dir：`C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs`
- run_count：`8`

## 2. Run-level 结果预览

```text
run_id,run_dir,case_id,policy,workload,seed,rps,max_requests,probe_events,probe_avg_duration,probe_min_duration,probe_max_duration,probe_p95_duration,invocation_events,function_count,schedule_events,scheduled_node_count,scheduled_nodes,schedule_success_rate,flow_events,flow_total_bytes,flow_total_duration,flow_avg_duration,replica_deployment_events,replica_node_count
default_skippy__low_load__seed_1,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\default_skippy__low_load__seed_1,default_skippy__low_load__seed_1,default_skippy,low_load,1,3,12,12,0.21851082224417187,0.1822677981217605,0.2477946989549786,0.2472812791022146,12,1,6,1,server_0,1.0,1,48000000,0.400230689634608,0.400230689634608,8,1
default_skippy__low_load__seed_2,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\default_skippy__low_load__seed_2,default_skippy__low_load__seed_2,default_skippy,low_load,2,3,12,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,12,1,6,1,server_10,1.0,1,48000000,0.400838708193524,0.400838708193524,8,1
default_skippy__medium_load__seed_1,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\default_skippy__medium_load__seed_1,default_skippy__medium_load__seed_1,default_skippy,medium_load,1,8,24,24,0.21900399596851172,0.1801684842680888,0.2556216556443137,0.2546792725602765,24,1,6,1,server_20,1.0,1,48000000,0.4003855581123624,0.4003855581123624,8,1
default_skippy__medium_load__seed_2,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\default_skippy__medium_load__seed_2,default_skippy__medium_load__seed_2,default_skippy,medium_load,2,8,24,24,0.2204746078892134,0.1821955885672655,0.2595855650359794,0.25640307616558783,24,1,6,1,server_30,1.0,1,48000000,0.4004827952471597,0.4004827952471597,8,1
fixed_node__low_load__seed_1,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\fixed_node__low_load__seed_1,fixed_node__low_load__seed_1,fixed_node,low_load,1,3,12,12,0.21851082224417187,0.1822677981217605,0.2477946989549786,0.2472812791022146,12,1,6,1,server_40,1.0,1,48000000,0.4005556466986283,0.4005556466986283,8,1
fixed_node__low_load__seed_2,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\fixed_node__low_load__seed_2,fixed_node__low_load__seed_2,fixed_node,low_load,2,3,12,12,0.2236463575649851,0.1845241094181446,0.2564827417511399,0.2561216432186243,12,1,6,1,server_50,1.0,1,48000000,0.4007925701848787,0.4007925701848787,8,1
fixed_node__medium_load__seed_1,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\fixed_node__medium_load__seed_1,fixed_node__medium_load__seed_1,fixed_node,medium_load,1,8,24,24,0.21900399596851172,0.1801684842680888,0.2556216556443137,0.2546792725602765,24,1,6,1,server_60,1.0,1,48000000,0.4003775157423326,0.4003775157423326,8,1
fixed_node__medium_load__seed_2,C:\Users\weew12\Downloads\faas-sim-master_内置依赖兼容性检查版\faas-sim-master\examples\batch_experiment\outputs\runs\fixed_node__medium_load__seed_2,fixed_node__medium_load__seed_2,fixed_node,medium_load,2,8,24,24,0.2204746078892134,0.1821955885672655,0.2595855650359794,0.25640307616558783,24,1,6,1,server_70,1.0,1,48000000,0.4003455088447389,0.4003455088447389,8,1
```

## 3. Policy / Workload 聚合摘要

```text
policy,workload,runs,avg_probe_events,avg_invocation_events,mean_probe_avg_duration,mean_probe_p95_duration,mean_flow_total_bytes,mean_scheduled_node_count
default_skippy,low_load,2,12.0,12.0,0.2210785899045785,0.25170146116041947,48000000.0,1.0
default_skippy,medium_load,2,24.0,24.0,0.21973930192886254,0.25554117436293217,48000000.0,1.0
fixed_node,low_load,2,12.0,12.0,0.2210785899045785,0.25170146116041947,48000000.0,1.0
fixed_node,medium_load,2,24.0,24.0,0.21973930192886254,0.25554117436293217,48000000.0,1.0
```

## 4. 策略对比结果

```text
workload,baseline_policy,policy,mean_probe_avg_duration_baseline,mean_probe_avg_duration_current,mean_probe_avg_duration_delta,mean_probe_avg_duration_relative,mean_probe_p95_duration_baseline,mean_probe_p95_duration_current,mean_probe_p95_duration_delta,mean_probe_p95_duration_relative,mean_flow_total_bytes_baseline,mean_flow_total_bytes_current,mean_flow_total_bytes_delta,mean_flow_total_bytes_relative
low_load,default_skippy,default_skippy,0.2210785899045785,0.2210785899045785,0.0,0.0,0.25170146116041947,0.25170146116041947,0.0,0.0,48000000.0,48000000.0,0.0,0.0
low_load,default_skippy,fixed_node,0.2210785899045785,0.2210785899045785,0.0,0.0,0.25170146116041947,0.25170146116041947,0.0,0.0,48000000.0,48000000.0,0.0,0.0
medium_load,default_skippy,default_skippy,0.21973930192886254,0.21973930192886254,0.0,0.0,0.25554117436293217,0.25554117436293217,0.0,0.0,48000000.0,48000000.0,0.0,0.0
medium_load,default_skippy,fixed_node,0.21973930192886254,0.21973930192886254,0.0,0.0,0.25554117436293217,0.25554117436293217,0.0,0.0,48000000.0,48000000.0,0.0,0.0
```

## 5. 说明

本报告由 `examples/experiment_analysis/main.py` 自动生成。默认情况下，脚本优先读取 `examples/batch_experiment/outputs/`，如果该目录不存在，则读取本样例自带的 `sample_results/`。
