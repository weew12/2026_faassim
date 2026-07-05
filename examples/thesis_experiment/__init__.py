"""
thesis_experiment 样例包。

本包用于组织一个面向论文实验的最小闭环样例，重点覆盖：
- 函数画像、节点状态、请求 trace 和实验 case 配置读取；
- load-only、FaasCache 和 cache-aware-joint 三类策略对比；
- 请求级冷启动、镜像拉取、数据拉取和网络延迟估计；
- R_cache、R_load 和 R_desired 决策日志；
- 候选节点评分、驱逐事件、策略摘要和 Markdown 实验报告导出。

运行入口：
    python -u examples/thesis_experiment/main.py
"""
