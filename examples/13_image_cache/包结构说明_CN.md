# image_cache 包结构说明

`image_cache` 是 faas-sim 节点级镜像缓存样例包，用于演示 docker.pull() 与 node_state.docker_images 的关系。

## 目录结构

```text
image_cache/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── scheduler.py
└── simulator.py
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册共享镜像；
4. 运行同节点缓存复用场景；
5. 运行不同节点冷拉取场景；
6. 导出场景结果和跨场景对比摘要。

### `scheduler.py`

序列固定节点调度器文件。

该文件提供：

```text
SequenceNodeScheduler
```

用于按照预设顺序把两个函数副本调度到同一节点或不同节点。

### `simulator.py`

镜像缓存观测模拟器文件。

该文件提供：

```text
ImageCacheSimulatorFactory
ImageCacheFunctionSimulator
```

其核心逻辑是在 `deploy()` 阶段调用 `docker.pull()` 前后检查节点镜像缓存状态，并记录 `image_cache_probe` 指标。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `image_cache_probe`、`flow`、`schedule` 等指标，并生成节点镜像缓存摘要和跨场景对比摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/image_cache/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的节点级镜像缓存机制，为后续镜像预拉取、冷启动优化和缓存状态感知调度提供基础。
