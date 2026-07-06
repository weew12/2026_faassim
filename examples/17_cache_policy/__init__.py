"""
cache_policy 样例包。

本包用于演示函数实例缓存策略的最小实验闭环，重点覆盖：
- 函数请求 trace；
- 函数冷启动代价与资源占用；
- warm hit / cold miss 判定；
- LRU、FIFO、Utility-aware 三类缓存策略；
- eviction、cache_state、request_result 和策略对比结果导出。

运行入口：
    python -u examples/17_cache_policy/main.py
"""
