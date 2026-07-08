# examples/basic

基础示例展示 faas-sim 最常见的 `Simulation + Benchmark` 工作流：创建拓扑、注册镜像、定义函数部署、部署副本并触发函数请求。

## 运行方式

在项目根目录执行：

```bash
python -u examples/basic/main.py
```

## 示例目标

- 使用 `UrbanSensingScenario` 创建基础拓扑。
- 在容器镜像仓库中注册 CPU/GPU 函数镜像。
- 部署 `python-pi` 和 `resnet50-inference` 两个函数。
- 等待函数副本可用后，并发触发 20 个请求。
- 为后续自定义函数模拟器、请求生成器、调度器和结果分析示例提供基础模板。

## 文件说明

- `main.py`：基础仿真入口，包含拓扑构造、benchmark 定义、部署和请求负载。
- `examples_basic_中文注释版.ipynb`：交互式中文注释版，适合逐步运行和查看指标表。
- `__init__.py`：包说明。

## 函数部署

| 函数 | 镜像 | 部署特点 |
| --- | --- | --- |
| `python-pi` | `python-pi-cpu` | 单 CPU 容器，使用默认伸缩配置。 |
| `resnet50-inference` | `resnet50-inference-gpu`, `resnet50-inference-cpu` | 同时提供 GPU/CPU 镜像，通过 `DeploymentRanking` 优先选择 GPU。 |

## 运行流程

1. `example_topology()` 创建拓扑并初始化 Docker registry。
2. `ExampleBenchmark.setup()` 注册各架构镜像。
3. `ExampleBenchmark.run()` 部署两个函数。
4. benchmark 等待 `python-pi` 和 `resnet50-inference` 副本可用。
5. benchmark 并发发起 10 个 `python-pi` 请求和 10 个 `resnet50-inference` 请求。
