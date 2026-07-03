# 内置 SimPy 替换说明

本版本把用户上传的 `simpy-master.zip` 中的 `src/simpy` 源码复制到 faas-sim 项目根目录，形成独立子包：

```text
faas-sim-master/simpy/
```

原 faas-sim 中的导入方式保持不变：

```python
import simpy
from simpy import Environment
from simpy.events import Event, Timeout, Process
```

由于 Python 会优先从项目根目录解析包名，运行 faas-sim 时会使用本项目内置的 `simpy` 包，而不是环境中通过 pip 安装的外部 SimPy 版本。

## 已同步调整

1. `requirements.txt` 中移除了外部 `simpy==3.0.11` 依赖，并加入中文说明，避免安装依赖时覆盖本地版本。
2. `setup.py` 中继续使用 `setuptools.find_packages()` 自动发现 `simpy` 子包，并把 `simpy/py.typed` 作为包数据保留。
3. 为 `simpy` 所有 Python 源文件重构中文业务语义注释，重点说明事件队列、进程恢复、超时事件、资源请求、队列资源和实时环境在仿真中的作用。

## 注意事项

用户上传的 SimPy 源码来自当前 `simpy-master.zip`，其接口与 faas-sim 原先锁定的 `simpy==3.0.11` 可能存在版本差异。本次处理保持 faas-sim 原业务代码导入方式不变，并通过语法编译和基础导入检查；若后续运行完整实验时发现行为差异，应优先围绕 `Environment`、`Process`、`Timeout`、`Resource` 和 `Store` 的兼容语义进行校准。
