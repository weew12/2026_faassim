"""
cache_aware_autoscaling 样例包。

本包用于演示缓存状态感知扩缩容的最小实验闭环，重点覆盖：
- 从函数状态时间序列读取请求负载、冷启动代价、warm 副本和当前副本数；
- 计算缓存需求副本数 R_cache；
- 计算负载需求副本数 R_load；
- 组合得到 R_desired = max(R_cache, R_load)；
- 输出扩缩容动作、容量约束状态、动作原因和时间序列摘要。

运行入口：
    python -u examples/cache_aware_autoscaling/main.py
"""
