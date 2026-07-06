"""
SimPy 共享资源包入口。

该目录提供三类常用资源抽象：
1. ``Resource`` 系列用于建模有限并发槽位，例如 CPU worker、连接池或函数实例可用槽；
2. ``Container`` 用于建模连续数值型容量，例如燃料、缓存容量、令牌或可用资源量；
3. ``Store`` 系列用于建模离散对象队列，例如消息队列、请求队列或待处理任务集合。

faas-sim 可以在函数模拟器、负载均衡器或扩展实验中复用这些资源对象表达排队、容量
限制和竞争关系。

注意：本文件**没有**任何 import 或 ``__all__``，也不做聚合导出。faas-sim 顶层
``simpy/__init__.py`` 通过显式 ``from simpy.resources.container import Container``
等方式把每个具体类直接 re-export 出去。因此本子包的"公开入口"实际上在
``simpy/__init__.py``，不在这里。
"""