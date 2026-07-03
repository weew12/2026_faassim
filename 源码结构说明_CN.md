# 内置 SimPy 离散事件仿真子包补充

本版本在项目根目录新增 `simpy/` 独立子包，用用户上传的 SimPy 源码替换原先的外部 `simpy==3.0.11` 依赖。faas-sim 中所有 `import simpy`、`from simpy...` 导入保持兼容，运行时优先解析到本项目内置实现。详见 `内置SimPy替换说明_CN.md` 与 `simpy/包结构说明_CN.md`。

# 内置 Skippy 调度子包补充

本版本在项目根目录新增 `skippy/` 独立子包，用用户上传的 Skippy Core 源码替换原先的外部 `edgerun-skippy-core` 依赖。faas-sim 中所有 `from skippy...` / `import skippy...` 导入保持兼容，运行时优先解析到本项目内置实现。详见 `内置Skippy替换说明_CN.md` 与 `skippy/包结构说明_CN.md`。

# 内置 Ether 网络仿真子包补充

本版本在项目根目录新增 `ether/` 独立子包，用用户上传的 Ether 源码替换原先的外部 `edgerun-ether` 依赖。faas-sim 中所有 `from ether...` / `import ether...` 导入保持兼容，运行时优先解析到本项目内置实现。详见 `内置Ether替换说明_CN.md` 与 `ether/包结构说明_CN.md`。

# faas-sim 源码结构说明（中文注释增强版）

本代码包在不改变原始业务逻辑、导入关系和函数签名的前提下，补充了更偏“业务语义”的中文注释。注释重点说明每个文件负责什么、每个类封装什么状态、每个函数推进什么流程，以及关键字段在仿真流程中的作用。

## 顶层目录

- `sim/`：核心仿真层，包含 FaaS 领域模型、默认平台实现、Benchmark、资源监控、指标记录、拓扑适配、Docker 镜像拉取和请求生成器。
- `sim/faas/`：FaaS 平台抽象与默认实现，覆盖函数定义、部署、副本生命周期、负载均衡和伸缩器。
- `sim/oracle/`：性能、资源、成本等估计器接口与经验分布实现。
- `ext/raith21/`：论文实验扩展层，提供真实画像数据、异构设备生成、拓扑生成、调度谓词/优先级和实验 Benchmark。
- `examples/`：示例层，演示基础仿真、自定义函数模拟器、自定义调度器、请求生成器和 watchdog 模型。
- `doc/`：官方 Sphinx 文档源码和图片资源。

## 主要业务链路

1. `Simulation.run()` 初始化 `Environment`，挂载拓扑、镜像仓库、FaaS 系统、调度器、指标器和后台进程。
2. `Benchmark.setup()` 注册镜像、装配函数部署和请求画像。
3. `DefaultFaasSystem.deploy()` 创建函数副本，将副本放入调度队列，并启动副本生命周期。
4. `run_scheduler_worker()` 调用调度器选择节点，之后 `simulate_function_start()` 推进 deploy/startup/setup。
5. 请求生成器调用 `env.faas.invoke()`，负载均衡器选择副本，`FunctionSimulator.invoke()` 采样执行时间和资源占用。
6. `Metrics` 和 `ResourceMonitor` 持续记录部署、调度、调用、资源和网络事件，实验结束后输出 DataFrame。

## 注释覆盖范围

- 所有 Python 文件：补充中文模块级文档注释。
- 所有类：补充中文类 docstring，说明业务职责、继承关系、核心字段和核心方法。
- 所有函数/方法：补充中文函数 docstring，说明作用、关键流程、参数和返回/产出。
- 类字段、模块配置字段、`self.xxx` 字段：在首次定义或赋值位置补充中文字段说明。
- 关键仿真语句：对 `env.timeout`、`env.process`、资源登记/释放、指标记录、部署、调用、伸缩等语句补充业务注释。

## 使用建议

阅读源码时建议按照 `sim/faas/core.py` → `sim/core.py` → `sim/faas/system.py` → `sim/faassim.py` → `sim/benchmark.py` → `sim/requestgen.py` → `sim/resource.py` → `sim/metrics.py` 的顺序理解核心链路；随后再看 `ext/raith21/` 中的函数画像、设备生成和调度策略扩展。
