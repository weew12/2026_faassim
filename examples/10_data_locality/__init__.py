"""
data_locality 样例包。

本包用于演示 faas-sim / Skippy 中的数据本地性机制，重点覆盖：
- StorageIndex 如何登记对象数据位置；
- FunctionContainer 标签如何声明输入数据路径；
- Skippy DataLocalityPriority 如何影响节点选择；
- simulate_data_download() 如何根据数据位置触发网络传输；
- 数据本地性调度与强制远端调度的结果对比。

运行入口：
    python -u examples/10_data_locality/main.py
"""
