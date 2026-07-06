# experiment_analysis 实验结果分析报告

## 1. 输入信息

- source_name：`sample_results`
- input_dir：`D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results`
- run_count：`8`

## 2. Run-level 结果预览

```text
run_id,run_dir,case_id,policy,workload,seed,rps,max_requests,probe_events,probe_avg_duration,probe_min_duration,probe_max_duration,probe_p95_duration,invocation_events,invocation_avg_duration,invocation_max_duration,function_count,schedule_events,scheduled_node_count,scheduled_nodes,schedule_success_rate,flow_events,flow_total_bytes,flow_total_duration,flow_avg_duration,replica_deployment_events
default_skippy__low_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\default_skippy__low_load__seed_1,default_skippy__low_load__seed_1,default_skippy,low_load,1,3,12,4,0.20249999999999999,0.18,0.22,0.2185,4,0.20249999999999999,0.22,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
default_skippy__low_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\default_skippy__low_load__seed_2,default_skippy__low_load__seed_2,default_skippy,low_load,2,3,12,4,0.20750000000000002,0.19,0.23,0.227,4,0.20750000000000002,0.23,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
default_skippy__medium_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\default_skippy__medium_load__seed_1,default_skippy__medium_load__seed_1,default_skippy,medium_load,1,8,24,4,0.23249999999999998,0.2,0.26,0.257,4,0.23249999999999998,0.26,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
default_skippy__medium_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\default_skippy__medium_load__seed_2,default_skippy__medium_load__seed_2,default_skippy,medium_load,2,8,24,4,0.2425,0.21,0.27,0.267,4,0.2425,0.27,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
fixed_node__low_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\fixed_node__low_load__seed_1,fixed_node__low_load__seed_1,fixed_node,low_load,1,3,12,4,0.235,0.21,0.26,0.257,4,0.235,0.26,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
fixed_node__low_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\fixed_node__low_load__seed_2,fixed_node__low_load__seed_2,fixed_node,low_load,2,3,12,4,0.245,0.22,0.27,0.267,4,0.245,0.27,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
fixed_node__medium_load__seed_1,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\fixed_node__medium_load__seed_1,fixed_node__medium_load__seed_1,fixed_node,medium_load,1,8,24,4,0.31,0.26,0.35,0.347,4,0.31,0.35,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
fixed_node__medium_load__seed_2,D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\15_experiment_analysis\sample_results\runs\fixed_node__medium_load__seed_2,fixed_node__medium_load__seed_2,fixed_node,medium_load,2,8,24,4,0.3225,0.27,0.36,0.357,4,0.3225,0.36,1,3,1,server_0,1.0,1,48000000,0.42,0.42,0
```

## 3. Policy / Workload 聚合摘要

```text
policy,workload,runs,avg_probe_events,avg_invocation_events,mean_probe_avg_duration,mean_probe_p95_duration,mean_invocation_avg_duration,mean_flow_total_bytes,mean_scheduled_node_count
default_skippy,low_load,2,4.0,4.0,0.20500000000000002,0.22275,0.20500000000000002,48000000.0,1.0
default_skippy,medium_load,2,4.0,4.0,0.2375,0.262,0.2375,48000000.0,1.0
fixed_node,low_load,2,4.0,4.0,0.24,0.262,0.24,48000000.0,1.0
fixed_node,medium_load,2,4.0,4.0,0.31625000000000003,0.352,0.31625000000000003,48000000.0,1.0
```

## 4. 策略对比结果

```text
workload,baseline_policy,policy,mean_probe_avg_duration_baseline,mean_probe_avg_duration_current,mean_probe_avg_duration_delta,mean_probe_avg_duration_relative,mean_probe_p95_duration_baseline,mean_probe_p95_duration_current,mean_probe_p95_duration_delta,mean_probe_p95_duration_relative,mean_invocation_avg_duration_baseline,mean_invocation_avg_duration_current,mean_invocation_avg_duration_delta,mean_invocation_avg_duration_relative,mean_flow_total_bytes_baseline,mean_flow_total_bytes_current,mean_flow_total_bytes_delta,mean_flow_total_bytes_relative
low_load,default_skippy,default_skippy,0.20500000000000002,0.20500000000000002,0.0,0.0,0.22275,0.22275,0.0,0.0,0.20500000000000002,0.20500000000000002,0.0,0.0,48000000.0,48000000.0,0.0,0.0
low_load,default_skippy,fixed_node,0.20500000000000002,0.24,0.034999999999999976,0.17073170731707304,0.22275,0.262,0.03925000000000001,0.1762065095398429,0.20500000000000002,0.24,0.034999999999999976,0.17073170731707304,48000000.0,48000000.0,0.0,0.0
medium_load,default_skippy,default_skippy,0.2375,0.2375,0.0,0.0,0.262,0.262,0.0,0.0,0.2375,0.2375,0.0,0.0,48000000.0,48000000.0,0.0,0.0
medium_load,default_skippy,fixed_node,0.2375,0.31625000000000003,0.07875000000000004,0.33157894736842125,0.262,0.352,0.08999999999999997,0.34351145038167924,0.2375,0.31625000000000003,0.07875000000000004,0.33157894736842125,48000000.0,48000000.0,0.0,0.0
```

## 5. 说明

本报告由 `examples/experiment_analysis/main.py` 自动生成。默认情况下，脚本优先读取 `examples/batch_experiment/outputs/`，如果该目录不存在，则读取本样例自带的 `sample_results/`。
