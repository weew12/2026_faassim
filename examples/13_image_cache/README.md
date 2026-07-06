# 13_image_cache：faas-sim 节点级镜像缓存样例

本样例用于演示 faas-sim 中节点级镜像缓存机制，重点展示 `docker.pull()`、`node_state.docker_images` 和 `flow.csv` 中 `docker_pull` 网络流之间的关系。

## 运行方式

将 `image_cache/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/13_image_cache/main.py
```

## 样例目标

该样例主要回答以下问题：

1. `docker.pull()` 如何检查节点本地镜像缓存；
2. 同一节点重复部署相同镜像时为什么第二次拉取耗时接近 0；
3. 不同节点首次部署相同镜像时为什么仍然需要各自拉取；
4. 镜像缓存命中如何影响 `flow.csv` 中的 `docker_pull` 网络流数量；
5. 如何导出并对比镜像缓存命中与冷拉取结果。

## 实验设计

样例运行两个场景：

```text
same_node_cache_reuse       两个函数使用同一镜像，且都调度到 server_0
different_node_cold_pull    两个函数使用同一镜像，分别调度到 server_0 和 server_1
```

两个函数都使用同一个镜像：

```text
image-cache-shared-cpu
```

因此：

```text
same_node_cache_reuse       第二次部署应命中 server_0 的镜像缓存
different_node_cold_pull    两个节点各自首次部署，应产生两次冷拉取
```

## 输出文件

运行结束后，结果会保存到：

```text
examples/13_image_cache/outputs/
```

每个场景有独立子目录：

```text
outputs/same_node_cache_reuse/
outputs/different_node_cold_pull/
```

主要结果文件包括：

```text
image_cache_probe.csv
image_cache_summary.csv
image_cache_node_summary.csv
flow.csv
schedule.csv
replica_deployment.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
invocations.csv
```

跨场景对比文件：

```text
outputs/image_cache_comparison.csv
```

## 结果解读

重点查看：

```text
image_cache_probe.csv
```

其中：

```text
cache_hit_before      docker.pull() 调用前节点是否已有镜像
pull_duration         本次拉取耗时
cached_image_count_after  拉取后节点镜像缓存数量
```

如果同节点缓存复用生效，`same_node_cache_reuse` 中第二个部署事件的 `cache_hit_before` 应为 `True`，并且 `pull_duration` 接近 0。

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
