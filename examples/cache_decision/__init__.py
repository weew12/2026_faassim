"""
cache_decision 样例包。

本包用于演示冷启动感知函数实例缓存决策过程，重点覆盖：
- 从函数画像快照读取请求量、冷启动代价、资源占用和副本状态；
- 计算冷启动收益、资源代价和缓存效用；
- 生成 keep_warm、prewarm_candidate、eviction_candidate、observe 四类缓存决策；
- 在容量预算约束下对保护对象和预热候选进行排序；
- 导出 decision detail、summary、rank 和 control hint。

运行入口：
    python -u examples/cache_decision/main.py
"""
