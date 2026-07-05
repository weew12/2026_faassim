"""
cache_aware_scheduler 样例包。

本包用于演示缓存状态感知调度的最小实验闭环，重点覆盖：
- 读取节点级函数 warm 实例缓存快照；
- 调度阶段识别目标函数是否已有 warm cache node；
- 在候选节点中融合 cache_hit、节点资源、数据路径估计等因素打分；
- 与默认 Skippy 调度进行对比；
- 导出 cache_aware_candidate、cache_aware_scheduler_result、request_probe 和对比摘要。

运行入口：
    python -u examples/cache_aware_scheduler/main.py
"""
