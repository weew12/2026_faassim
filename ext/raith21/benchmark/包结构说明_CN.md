# `ext/raith21/benchmark` 包结构说明

Raith21 Benchmark 包：封装具体实验场景。

## 包内 Python 文件

- `__init__.py`：该文件参与本包对应的仿真支撑逻辑。
- `constant.py`：恒定工作负载 Benchmark，按实验配置选择函数组合、部署函数并持续产生固定强度请求。
