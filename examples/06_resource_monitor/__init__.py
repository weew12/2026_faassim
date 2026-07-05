"""
resource_monitor 样例包。

本包用于演示 faas-sim 原生资源监控能力，重点覆盖：
- ResourceState 中 CPU / 内存资源占用的登记与释放；
- ResourceMonitor 如何周期性采集资源状态；
- 函数副本执行期间节点资源使用如何变化；
- resource、invocations、replica_deployment 等指标导出。

运行入口：
    python -u examples/resource_monitor/main.py
"""
