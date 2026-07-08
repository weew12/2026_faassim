# examples/custom_function_sim

本示例演示如何实现自定义 `FunctionSimulator`，并通过 `SimulatorFactory` 接入 faas-sim 的函数部署和调用流程。

## 运行方式

在项目根目录执行：

```bash
python -u examples/custom_function_sim/main.py
```

## 示例目标

- 复用 `examples.basic` 的拓扑和 benchmark。
- 使用 `CustomSimulatorFactory` 替换默认函数模拟器工厂。
- 实现 `deploy`、`startup`、`setup`、`invoke`、`teardown` 生命周期方法。
- 在 `invoke` 中登记临时 CPU 占用，并按函数名/节点类型设置不同执行耗时。

## 文件说明

- `main.py`：自定义模拟器工厂、函数生命周期模拟器和运行入口。
- `examples_custom_function_sim_中文注释版.ipynb`：交互式中文注释版。
- `__init__.py`：包说明。

## 生命周期含义

| 方法 | 示例行为 |
| --- | --- |
| `deploy` | 通过 `docker.pull` 模拟镜像拉取。 |
| `startup` | 固定等待 10 个仿真时间单位，模拟容器启动。 |
| `setup` | 保留初始化阶段接口，当前不额外等待。 |
| `invoke` | 模拟请求执行，登记/释放 10% CPU 占用。 |
| `teardown` | 保留关闭阶段接口，当前不额外等待。 |

## 执行耗时规则

- `python-pi` 在 `rpi3*` 节点上执行 20 个仿真时间单位。
- `python-pi` 在其他节点上执行 2 个仿真时间单位。
- `resnet50-inference` 执行 0.5 个仿真时间单位。
- 未匹配函数名的请求执行 0 个仿真时间单位。
