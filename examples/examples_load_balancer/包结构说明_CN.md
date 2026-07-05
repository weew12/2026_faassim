# examples_load_balancer 包结构说明

`examples_load_balancer` 是 faas-sim 原生负载均衡功能样例包，用于演示请求如何在多个函数副本之间分发。

## 目录结构

```text
examples_load_balancer/
├── notebook/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── load_balancer.py
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
3. 构造拥有 3 个副本的 `FunctionDeployment`；
4. 创建 `Simulation`；
5. 启用可观测轮询负载均衡器；
6. 触发请求负载；
7. 导出负载均衡结果指标。

### `load_balancer.py`

负载均衡策略文件。

该文件提供：

```text
InstrumentedRoundRobinLoadBalancer
```

它保持轮询负载均衡语义，同时把每次请求路由决策写入 `load_balancer` 指标。

### `system.py`

FaaS 系统创建文件。

该文件提供 `create_load_balancer_faas_system(env)`，用于创建 `DefaultFaasSystem` 并替换其 `load_balancer` 字段。

### `simulator.py`

函数执行模拟器文件。

该文件提供稳定函数执行时间，便于观察请求路由分布，而不是把实验差异混入执行模型。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `load_balancer`、`invocations`、`schedule` 等 DataFrame，并生成路由摘要。

### `notebook/`

Jupyter 运行示例目录。

Notebook 采用上一个自动伸缩样例中已验证可用的“命令行等价运行版”写法。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/examples_load_balancer/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的负载均衡行为，为后续缓存状态感知请求路由和缓存命中优先调度提供基础。
