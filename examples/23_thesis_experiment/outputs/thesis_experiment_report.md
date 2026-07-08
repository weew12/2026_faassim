# Thesis Experiment Report

## Policy Summary

```text
case_id,policy_name,request_count,warm_hits,warm_misses,image_cache_hits,data_cache_hits,avg_latency,p95_latency,total_latency,total_cold_start_penalty,total_image_pull_penalty,total_data_fetch_penalty,avg_r_cache,avg_r_load,avg_r_desired,avg_cache_used,warm_hit_rate,image_cache_hit_rate,data_cache_hit_rate,eviction_count
cache_aware_joint,CacheAwareJoint,35,20,15,30,30,0.8547428571428571,3.165599999999997,29.916,17.55,3.9,2.1,0.9714285714285714,1.0,1.0,4.628571428571429,0.5714285714285714,0.8571428571428571,0.8571428571428571,12
faascache,FaasCache,35,19,16,13,13,1.4409714285714286,5.1624,50.434,19.45,15.9,8.5,0.9714285714285714,0.0,0.9714285714285714,4.628571428571429,0.5428571428571428,0.37142857142857144,0.37142857142857144,13
load_only,LoadOnly,35,7,28,13,13,1.9095428571428572,5.1624,66.834,35.85,15.9,8.5,0.0,1.0,1.0,2.4571428571428573,0.2,0.37142857142857144,0.37142857142857144,27
```

## Comparison with LoadOnly

```text
case_id,policy_name,avg_latency,avg_latency_change_vs_load_only,total_cold_start_penalty,cold_start_reduction_vs_load_only,warm_hit_rate,warm_hit_rate_delta_vs_load_only
cache_aware_joint,CacheAwareJoint,0.8547428571428571,0.5523835173713979,17.55,0.5104602510460251,0.5714285714285714,0.3714285714285714
faascache,FaasCache,1.4409714285714286,0.24538408594427988,19.45,0.4574616457461646,0.5428571428571428,0.3428571428571428
load_only,LoadOnly,1.9095428571428572,0.0,35.85,0.0,0.2,0.0
```

## Phase Summary

```text
case_id,policy_name,phase,request_count,warm_hit_rate,avg_latency,p95_latency,total_cold_start_penalty
cache_aware_joint,CacheAwareJoint,burst,15,0.7333333333333333,0.5648,2.868,5.5
cache_aware_joint,CacheAwareJoint,cooldown,10,0.6,0.5237999999999999,1.7564999999999973,3.45
cache_aware_joint,CacheAwareJoint,warmup,10,0.3,1.6206,4.579399999999999,8.6
faascache,FaasCache,burst,15,0.7333333333333333,1.2621333333333336,5.1610000000000005,5.5
faascache,FaasCache,cooldown,10,0.5,1.2578,3.855349999999997,5.35
faascache,FaasCache,warmup,10,0.3,1.8923999999999999,4.574999999999998,8.6
load_only,LoadOnly,burst,15,0.3333333333333333,1.8821333333333332,5.1610000000000005,14.8
load_only,LoadOnly,cooldown,10,0.0,1.8878,4.593349999999998,11.649999999999999
load_only,LoadOnly,warmup,10,0.2,1.9723999999999997,4.574999999999998,9.399999999999999
```

## 论文 demo 关键摘要 (Paper Highlight)

```text
metric,value,note
warm_hit_rate__cache_aware_joint,0.5714285714285714,cache_aware_joint (CacheAwareJoint) 函数 warm 实例命中率（论文 demo 关键指标）
image_cache_hit_rate__cache_aware_joint,0.8571428571428571,cache_aware_joint 镜像缓存命中率（避免镜像拉取）
data_cache_hit_rate__cache_aware_joint,0.8571428571428571,cache_aware_joint 数据缓存命中率（避免数据获取）
avg_latency__cache_aware_joint,0.8547428571428571,cache_aware_joint 平均每次 invoke latency
p95_latency__cache_aware_joint,3.165599999999997,cache_aware_joint p95 latency（论文 demo 重要 tail-latency 指标）
total_cold_start_penalty__cache_aware_joint,17.55,cache_aware_joint 全部冷启动惩罚累加
avg_r_cache__cache_aware_joint,0.9714285714285714,cache_aware_joint 平均 R_cache（cache 驱动的副本需求）
avg_r_load__cache_aware_joint,1.0,cache_aware_joint 平均 R_load（负载驱动的副本需求）
avg_r_desired__cache_aware_joint,1.0,"cache_aware_joint 平均 R_desired = max(R_cache, R_load)"
eviction_count__cache_aware_joint,12.0,cache_aware_joint 全部 evict 事件数
warm_hit_rate__faascache,0.5428571428571428,faascache (FaasCache) 函数 warm 实例命中率（论文 demo 关键指标）
image_cache_hit_rate__faascache,0.37142857142857144,faascache 镜像缓存命中率（避免镜像拉取）
data_cache_hit_rate__faascache,0.37142857142857144,faascache 数据缓存命中率（避免数据获取）
avg_latency__faascache,1.4409714285714286,faascache 平均每次 invoke latency
p95_latency__faascache,5.1624,faascache p95 latency（论文 demo 重要 tail-latency 指标）
total_cold_start_penalty__faascache,19.45,faascache 全部冷启动惩罚累加
avg_r_cache__faascache,0.9714285714285714,faascache 平均 R_cache（cache 驱动的副本需求）
avg_r_load__faascache,0.0,faascache 平均 R_load（负载驱动的副本需求）
avg_r_desired__faascache,0.9714285714285714,"faascache 平均 R_desired = max(R_cache, R_load)"
eviction_count__faascache,13.0,faascache 全部 evict 事件数
warm_hit_rate__load_only,0.2,load_only (LoadOnly) 函数 warm 实例命中率（论文 demo 关键指标）
image_cache_hit_rate__load_only,0.37142857142857144,load_only 镜像缓存命中率（避免镜像拉取）
data_cache_hit_rate__load_only,0.37142857142857144,load_only 数据缓存命中率（避免数据获取）
avg_latency__load_only,1.9095428571428572,load_only 平均每次 invoke latency
p95_latency__load_only,5.1624,load_only p95 latency（论文 demo 重要 tail-latency 指标）
total_cold_start_penalty__load_only,35.85,load_only 全部冷启动惩罚累加
avg_r_cache__load_only,0.0,load_only 平均 R_cache（cache 驱动的副本需求）
avg_r_load__load_only,1.0,load_only 平均 R_load（负载驱动的副本需求）
avg_r_desired__load_only,1.0,"load_only 平均 R_desired = max(R_cache, R_load)"
eviction_count__load_only,27.0,load_only 全部 evict 事件数
avg_latency_reduction__cache_aware_joint_vs_load_only,0.5523835173713979,CacheAwareJoint 相对 LoadOnly 平均延迟降低比例（论文 demo 关键数字）
cold_start_penalty_reduction__cache_aware_joint_vs_load_only,0.5104602510460251,CacheAwareJoint 相对 LoadOnly 冷启动惩罚降低比例（论文 demo 关键数字）
image_cache_hit_rate_improvement__cache_aware_joint_vs_load_only,0.48571428571428565,CacheAwareJoint 相对 LoadOnly 镜像缓存命中率提升
data_cache_hit_rate_improvement__cache_aware_joint_vs_load_only,0.48571428571428565,CacheAwareJoint 相对 LoadOnly 数据缓存命中率提升
avg_latency_reduction__cache_aware_joint_vs_faascache,0.40682872665265496,CacheAwareJoint 相对 FaasCache 平均延迟降低比例（论文 demo 关键证据：cache-aware 调度胜出）
image_cache_hit_rate_improvement__cache_aware_joint_vs_faascache,0.48571428571428565,CacheAwareJoint 相对 FaasCache 镜像缓存命中率提升
data_cache_hit_rate_improvement__cache_aware_joint_vs_faascache,0.48571428571428565,CacheAwareJoint 相对 FaasCache 数据缓存命中率提升
r_dominant_max__cache_aware_joint,1.0,"CacheAwareJoint R_dominant = max(avg_r_cache, avg_r_load)"
r_dominant_source__cache_aware_joint,1.0,"CacheAwareJoint R_dominant 来源（1=R_load, 0=R_cache）"
r_dominant_max__load_only,1.0,"LoadOnly R_dominant = max(avg_r_cache, avg_r_load)（应 = avg_r_load）"
r_dominant_source__load_only,1.0,LoadOnly R_dominant 来源（应 = 1 R_load）
r_dominant_max__faascache,0.9714285714285714,"FaasCache R_dominant = max(avg_r_cache, avg_r_load)（应 = avg_r_cache）"
r_dominant_source__faascache,0.0,FaasCache R_dominant 来源（应 = 0 R_cache）
result_candidate_consistency,1.0,result × candidate join match 占比（论文 demo 关键证据，应 1.0）
result_candidate_matched,105.0,matched 行数
result_candidate_total,105.0,join 总行数（应 == 3 case × 35 request = 105）
request_decision_consistency,1.0,request × decision join match 占比（论文 demo 关键证据，应 1.0）
request_decision_matched,105.0,matched 行数
request_decision_total,105.0,join 总行数（应 == 3 case × 35 request = 105）
```

## Notes

- `R_cache` represents cache-driven warm replica demand.
- `R_load` represents load-driven replica demand.
- `CacheAwareJoint` combines both terms using `R_desired = max(R_cache, R_load)` and uses cache-aware node scoring.
- This example is trace-driven and independent from faas-sim core APIs, so it is stable across local source versions.
- `result_candidate_join` 验证 selected_node 是 max-score node，且 cache_hit 一致
- `request_decision_join` 验证 result 跟 decision 的 r_cache / r_load / r_desired 一致