# 内置 Skippy 替换说明

本版本已将用户上传的 `skippy-core-master.zip` 作为独立 Python 子包合入 faas-sim 项目根目录，形成：

```text
faas-sim-master/
├── skippy/             # 本地内置 Skippy 调度器子包
├── ether/              # 本地内置 Ether 网络仿真包
├── sim/                # faas-sim 主体仿真代码
├── ext/                # 论文实验扩展代码
└── examples/           # 示例实验
```

原始 faas-sim 代码中的导入形式保持不变：

```python
from skippy.core.scheduler import Scheduler
from skippy.core.model import Pod, Node
from skippy.core.storage import StorageIndex
```

因此，faas-sim 的调度适配层 `sim/skippy.py`、实验扩展层 `ext/raith21/` 以及示例代码无需大规模修改。只要从项目根目录运行，或执行 `pip install -e .` 安装当前项目，Python 会优先使用项目内置的 `skippy` 包。

## 已做的兼容处理

1. 删除 `requirements.txt` 中的 `edgerun-skippy-core>=0.1.1` 外部依赖，避免安装时继续拉取旧版本 Skippy。
2. 保留 `setup.py` 中的 `setuptools.find_packages()`，使 `skippy` 能作为独立包随 faas-sim 一起安装。
3. 对 `skippy` 所有 Python 文件补充中文业务语义注释，说明文件职责、类职责、字段含义、函数流程和调度关键语句。
4. 保持原始类名、函数名、导入路径和调度算法流程不变，使 faas-sim 原有代码仍可直接调用。

## Skippy 在 faas-sim 中的位置

在 faas-sim 的部署流程中，`DefaultFaasSystem` 创建函数副本后，会通过 `sim/skippy.py` 将函数副本转换为 Skippy 的 `Pod` 对象，将 Ether 拓扑节点转换为 Skippy 的 `Node` 对象。随后 `Scheduler.schedule()` 执行谓词过滤和优先级打分，返回建议节点、可行节点数量和需要拉取的镜像列表。faas-sim 再根据该结果推进镜像拉取、函数启动、setup 和请求执行等生命周期仿真。

## 验证结果

已执行 `python -m compileall` 语法检查。当前沙箱环境缺少 `simpy` 等运行依赖，因此未执行完整仿真实验运行；但内置 `skippy` 源码自身通过了 Python 语法编译检查。
