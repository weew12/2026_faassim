# 官方文档离线化覆盖检查

本文件用于说明官方文档内容与离线 Markdown 文件之间的对应关系，避免替换文档时遗漏页面或资源。

| 原文档源文件 | 离线文件 | 覆盖内容 |
| --- | --- | --- |
| `contents.rst` | `contents.md` | 文档目录、原 Sphinx 索引与搜索说明、离线图片资源索引 |
| `index.rst` | `index.md` | faas-sim 总览、架构、SimPy/Ether/Skippy、trace-driven 特征、背景 |
| `concepts/index.rst` | `concepts/index.md` | Domain model、Function、FunctionImage、FunctionDeployment、FunctionContainer、FunctionReplica、Node、FaaS System、FunctionSimulator、Simulation、Topology、Benchmark、Request generators、公式说明、提示信息 |
| `system/index.rst` | `system/index.md` | DefaultFaasSystem 内部机制、FaasSystem 方法、内部状态字段、资源接口、CPU 资源消耗示例、Resource Monitor 与 MetricsServer |
| `analysis/index.rst` | `analysis/index.md` | DataFrame 提取、默认日志列表、Metrics、RuntimeLogger、Clock、sim.logging 提示 |
| `function_sims/index.rst` | `function_sims/index.md` | FunctionSimulator 说明、OpenFaaS Watchdog、Forking/HTTP 模式、Watchdog 抽象方法、HTTPWatchdog 队列机制、ForkingWatchdog 资源风险、调用过程图 |
| `examples/index.rst` | `examples/index.md` | 示例代码位置说明 |

## 保留的图片资源

- `figures/architecture-overview.png`
- `figures/function-conceptual-view.png`
- `figures/workload-generators.png`
- `figures/functionsim-invoke-times.png`
- `figures/default-faas-system-components.jpg`
- `_static/logo-h150.png`
- `_static/logo-paths.svg`
- `_static/logo.png`

## 处理说明

- 原有 reStructuredText 页面已替换为 Markdown 页面。
- 原有 Sphinx 构建文件不再保留，因为当前目标是离线 Markdown 阅读，而不是重新构建 HTML。
- 原文档中的外部链接均保留为 Markdown 链接。
- 原文档中的代码块、提示、注意事项、公式和图片说明均已转写为中文 Markdown。
