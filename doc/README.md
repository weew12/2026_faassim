# faas-sim 离线中文官方文档

本目录用于替换项目原有的 Sphinx 在线构建文档，内容根据 faas-sim 官方文档页面整理为可直接离线阅读的 Markdown 版本。文档覆盖原官方目录中的全部页面：Overview、Concepts、System、Analysis、Function Simulators 和 Examples，并保留原有图片资源。

## 阅读入口

| 原官方页面 | 离线 Markdown 文件 | 内容说明 |
| --- | --- | --- |
| Documentation for faas-sim | [contents.md](contents.md) | 离线目录、页面索引与图片资源索引 |
| faas-sim Overview | [index.md](index.md) | faas-sim 总览、架构与背景 |
| Concepts | [concepts/index.md](concepts/index.md) | 领域模型、FaaS System、函数仿真器、仿真与请求生成器 |
| System | [system/index.md](system/index.md) | DefaultFaasSystem 内部状态、资源使用接口与资源监控 |
| Analysis | [analysis/index.md](analysis/index.md) | 指标日志、默认 DataFrame 名称与 Metrics 机制 |
| Function Simulators | [function_sims/index.md](function_sims/index.md) | OpenFaaS Watchdog 风格函数仿真器、HTTP/Forking 模式 |
| Examples | [examples/index.md](examples/index.md) | 示例代码位置说明 |

## 离线资源

图片资源保留在以下目录：

```text
figures/
_static/
```

Markdown 文档中的图片链接均使用相对路径，可在本地编辑器、GitHub、VS Code、Typora 或普通 Markdown 预览器中直接查看。

## 与原文档的关系

原项目的 `doc` 目录使用 Sphinx、reStructuredText、ReadTheDocs 主题和在线构建流程。本次替换后，文档不再依赖 Sphinx 构建，重点服务于离线阅读、源码学习和论文实验环境中的本地查阅。原文档中的 `genindex` 和 `search` 属于 Sphinx 自动生成页面，Markdown 版本中以目录索引和编辑器全文搜索替代。
