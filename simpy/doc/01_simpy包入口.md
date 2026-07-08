# 01 · simpy 包入口

对应源码：`simpy/__init__.py`

## 1. 文件定位

`__init__.py` 是公开 API 聚合层，不实现仿真逻辑。它把核心类从各子模块导入并重新暴露，让调用方可以使用标准 SimPy 写法：

```python
import simpy

env = simpy.Environment()
store = simpy.Store(env)
```

## 2. 公开对象

| 类别 | 对象 | 来源 |
| --- | --- | --- |
| 环境 | `Environment`, `RealtimeEnvironment` | `core.py`, `rt.py` |
| 事件 | `Event`, `Timeout`, `Process`, `AllOf`, `AnyOf` | `events.py` |
| 异常 | `SimPyException`, `Interrupt` | `exceptions.py` |
| 槽位资源 | `Resource`, `PriorityResource`, `PreemptiveResource` | `resources/resource.py` |
| 连续容量 | `Container` | `resources/container.py` |
| 对象队列 | `Store`, `PriorityStore`, `FilterStore`, `PriorityItem` | `resources/store.py` |

这些对象同时出现在 `__all__` 中，因此 `from simpy import *` 只会导出这批稳定 API。

## 3. `_toc` 与 `_compile_toc`

源码中 `_toc` 把公开对象按语义分组，`_compile_toc()` 将它转换成 Sphinx autosummary 风格文本，并注入模块 docstring。这个机制只影响 `help(simpy)` 和文档展示，不参与仿真运行。

最后的断言：

```python
assert set(__all__) == {obj.__name__ for _, objs in _toc for obj in objs}
```

用于保证公开 API 清单与文档目录一致。新增公开对象时必须同时更新 `__all__` 和 `_toc`。

## 4. 版本字段

`__version__` 优先读取当前 Python 环境中的 `simpy` 包 metadata；如果项目以内置源码方式运行且没有安装外部发行包，则使用 `'embedded'`。

## 5. 源码阅读提示

读 `__init__.py` 时不要寻找事件循环。真正的行为在这些文件中：

- `core.py`：事件队列和仿真时钟
- `events.py`：事件状态、进程恢复、条件组合
- `resources/*.py`：资源请求与排队

`__init__.py` 的价值在于确定“外部能用什么”和“对象来自哪里”。

