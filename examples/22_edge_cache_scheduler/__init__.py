"""
edge_cache_scheduler 样例包。

本包用于演示边缘缓存感知调度的最小实验闭环，重点覆盖：
- 节点状态、函数画像、缓存快照和请求 trace 读取；
- 同时考虑函数 warm 实例缓存、镜像缓存、数据缓存、边缘区域亲和性和节点负载；
- 与缓存无感知 round-robin 调度进行对比；
- 导出候选节点评分、请求级调度结果、缓存命中统计和策略对比摘要。

运行入口：
    python -u examples/22_edge_cache_scheduler/main.py
"""
