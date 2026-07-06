"""
cold_start_aware_policy 样例包。

本包用于演示冷启动感知函数实例保活策略，重点覆盖：
- 请求 trace 驱动的函数实例 warm / cold 状态演化；
- 固定 keep-alive 策略与冷启动感知 keep-alive 策略对比；
- 基于冷启动代价、近期访问频率和资源占用计算保活效用；
- 在容量预算下执行保活、延长、过期和驱逐决策；
- 导出请求结果、策略决策、驱逐事件和策略摘要。

运行入口：
    python -u examples/21_cold_start_aware_policy/main.py
"""
