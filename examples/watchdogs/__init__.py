"""
OpenFaaS watchdog 执行模型示例包。

该包演示如何为不同函数绑定不同的 FunctionSimulator：
- ForkingWatchdog：适合训练、批处理等每次请求独立执行的任务。
- HTTPWatchdog：适合推理、Web handler 等通过固定 worker 池处理请求的任务。
"""

