"""
network_flow 样例包。

本包用于演示 faas-sim / Ether 原生网络流仿真能力，重点覆盖：
- 自定义网络拓扑；
- 节点、链路和透明交换节点的连接方式；
- Ether Flow 的传输时间模拟；
- 多个 Flow 竞争同一瓶颈链路时的带宽共享；
- flow、route、summary 等 CSV 结果导出。

运行入口：
    python -u examples/network_flow/main.py
"""
