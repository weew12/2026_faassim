# examples_autoscaling 包结构说明

`examples_autoscaling` 是 faas-sim 原生自动伸缩功能样例包，用于演示自动伸缩闭环如何在仿真中运行。

## 目录结构

```text
examples_autoscaling/
├── notebook/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── simulator.py
└── system.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 注册函数镜像；
3. 构造 `FunctionDeployment`；
4. 设置 `ScalingConfiguration`；
5. 创建 `Simulation`；
6. 启用自动伸缩 FaaS 系统；
7. 运行请求负载；
8. 导出结果指标。

### `system.py`

FaaS 系统创建文件。

该文件提供 `create_autoscaling_faas_system(env)`，用于创建：

```python
DefaultFaasSystem(env, scale_by_average_requests=True)
```

这样 faas-sim 就会启用基于平均请求负载的原生自动伸缩逻辑。

### `simulator.py`

函数执行模拟器文件。

该文件提供：

```text
AutoscalingSimulatorFactory
AutoscalingFunctionSimulator
```

用于模拟函数副本的部署、启动、调用和关闭过程。

### `analysis.py`

指标导出与分析文件。

该文件负责从 `sim.env.metrics` 中提取常用 DataFrame，并保存到 `outputs/` 目录。

### `notebook/`

Jupyter 运行示例目录。

Notebook 采用“首格代码自检”结构，避免 Windows + Jupyter 环境下无输出的问题。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/examples_autoscaling/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”，优先级高于论文定制功能样例。

它用于补齐官方 examples 中没有系统展示的自动伸缩闭环，为后续实现缓存状态感知扩缩容提供基础。
