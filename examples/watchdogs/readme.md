# examples/watchdogs

本示例演示 faas-sim 中的 OpenFaaS watchdog 执行模型：同一个实验同时部署训练函数和推理函数，并为它们绑定不同的 `FunctionSimulator`。

## 运行方式

在项目根目录执行：

```bash
python -u examples/watchdogs/main.py
```

## 示例目标

- 展示 `SimulatorFactory` 如何按函数镜像选择模拟器。
- 对比 `ForkingWatchdog` 和 `HTTPWatchdog` 的请求执行语义。
- 观察函数部署、镜像拉取、副本启动、请求执行和 FET 指标记录流程。

## 文件说明

- `main.py`：示例入口，定义 benchmark、镜像、函数部署和请求负载。
- `training.py`：训练函数模拟器，继承 `ForkingWatchdog`。
- `inference.py`：推理函数模拟器，继承 `HTTPWatchdog`。
- `__init__.py`：包说明。

## Watchdog 模式

| 函数 | 模拟器 | 执行含义 |
| --- | --- | --- |
| `resnet50-training` | `TrainingFunctionSim(ForkingWatchdog)` | 每个请求独立进入 claim / execute / release 流程，适合训练或长任务示例。 |
| `resnet50-inference` | `InferenceFunctionSim(HTTPWatchdog)` | 副本内部有固定 worker 队列，本示例为 4 个 worker，适合推理服务示例。 |

## 关键流程

1. `TrainInferenceBenchmark.setup()` 注册训练和推理镜像。
2. `TrainInferenceBenchmark.run()` 部署两个函数并等待副本可用。
3. `AIFunctionSimulatorFactory.create()` 根据镜像名选择训练或推理模拟器。
4. benchmark 并发提交 10 个训练请求和 10 个推理请求。
5. 仿真结束后可从 metrics 的 `fets` 表查看每次函数执行的时间区间。
