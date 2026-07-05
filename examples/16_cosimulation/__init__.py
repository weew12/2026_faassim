"""
cosimulation 样例包。

本包用于演示 faas-sim 与外部控制/环境模型的协同仿真组织方式，重点覆盖：
- 外部 trace 驱动的环境状态输入；
- faas-sim 离散事件仿真与外部控制循环之间的状态交换；
- 外部状态对函数运行时间的影响；
- cosim_exchange、cosim_phase、cosim_invoke_probe 等指标导出；
- 为后续与外部调度器、强化学习控制器或网络仿真器联动提供最小模板。

运行入口：
    python -u examples/cosimulation/main.py
"""
