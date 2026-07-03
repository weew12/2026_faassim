# 内置 Ether 替换说明

本版本已将用户上传的 `ether-master.zip` 作为独立 Python 子包合入 faas-sim 项目根目录，形成：

```text
faas-sim-master/
├── ether/              # 本地内置 Ether 网络仿真包
├── sim/                # faas-sim 主体仿真代码
├── ext/                # 论文实验扩展代码
└── examples/           # 示例实验
```

原始 faas-sim 代码中使用的导入形式仍为：

```python
from ether.core import Node, Link, Flow
import ether.scenarios.urbansensing as scenario
```

因此不需要大规模修改业务代码。只要从项目根目录运行，或通过 `pip install -e .` 安装当前项目，Python 会优先使用项目内置的 `ether` 包。

## 已做的兼容性处理

1. 删除 `requirements.txt` 中的 `edgerun-ether>=0.3.1` 外部依赖，避免安装时继续拉取旧版本 Ether。
2. 在 `setup.py` 中保留 `setuptools.find_packages()`，使 `ether` 能作为独立包被发现；同时增加 graphml 数据文件的 package_data 配置。
3. 修复 `ether/cell.py` 在新版本 Python 中 `collections.Iterable` 导入失败的问题，改为从 `collections.abc` 导入。
4. 修复 `ether/export.py` 中裸导入 `topology/core` 的问题，改为包内绝对导入 `ether.topology` 和 `ether.core`。
5. 对 `ether` 所有 Python 文件补充中文业务语义注释，说明文件职责、类职责、字段含义、函数流程和关键仿真语句。

## 验证结果

已执行 `python -m compileall` 语法检查，并完成本地导入 smoke test，确认内置 `ether` 包可以被 faas-sim 代码导入。
