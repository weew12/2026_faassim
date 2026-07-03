# `examples/watchdogs` 包结构说明

watchdog 执行模式示例包。

## 包内 Python 文件

- `__init__.py`：该文件参与本包对应的仿真支撑逻辑。
- `inference.py`：推理函数模拟器示例，模拟模型加载、推理资源占用和请求执行耗时。
- `main.py`：watchdog 示例入口，组合训练和推理函数模拟器，展示 OpenFaaS HTTP/Fork 风格执行模型。
- `training.py`：训练函数模拟器示例，模拟训练任务的启动、资源占用、执行和释放过程。
