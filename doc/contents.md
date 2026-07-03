# faas-sim 文档目录

本文件对应原官方文档中的 `contents.rst`，用于提供离线 Markdown 版本的完整目录。

## 文档页面

1. [faas-sim 总览](index.md)
2. [核心概念](concepts/index.md)
3. [系统实现](system/index.md)
4. [结果分析](analysis/index.md)
5. [函数仿真器](function_sims/index.md)
6. [示例](examples/index.md)

## 原 Sphinx 索引与搜索的离线替代

原 Sphinx 文档包含 `Indices and tables`，其中有 `genindex` 和 `search` 两个自动生成入口。离线 Markdown 版本不再生成 HTML 索引页，因此使用以下方式替代：

- 通过本目录的页面目录进入各章节；
- 使用编辑器或 IDE 的全文搜索功能检索关键类、函数、概念和路径；
- 结合项目中的中文源码注释、包结构说明文件和本目录文档进行源码学习。

## 图片资源索引

| 图片文件 | 使用位置 | 说明 |
| --- | --- | --- |
| `figures/architecture-overview.png` | [faas-sim 总览](index.md) | faas-sim 高层架构概览 |
| `figures/function-conceptual-view.png` | [核心概念](concepts/index.md) | 函数、镜像、部署、容器、实例与节点的领域模型 |
| `figures/workload-generators.png` | [核心概念](concepts/index.md) | 到达过程与负载模式组合形成请求负载 |
| `figures/functionsim-invoke-times.png` | [函数仿真器](function_sims/index.md) | HTTPWatchdog 调用过程中的日志事件与组件交互 |
| `figures/default-faas-system-components.jpg` | 保留资源 | DefaultFaasSystem 组件结构图，便于后续扩展说明 |
| `_static/logo-h150.png` | [faas-sim 总览](index.md) | faas-sim 标识图片 |
