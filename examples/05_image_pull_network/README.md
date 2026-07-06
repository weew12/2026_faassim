# image_pull_network：faas-sim 镜像拉取网络样例

本样例用于演示 faas-sim 中 `docker.pull()` 与网络传输之间的关系，重点展示首次镜像拉取、同节点镜像缓存复用以及镜像大小对拉取耗时的影响。

## 运行方式

将 `image_pull_network/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/image_pull_network/main.py
```

## 样例目标

该样例主要回答以下问题：

1. `docker.pull()` 如何触发网络 Flow；
2. `flow.csv` 中的 `action_type=docker_pull` 表示什么；
3. 同一节点第一次部署某个镜像时为什么需要拉取；
4. 同一节点再次部署相同镜像时为什么可以复用缓存；
5. 镜像大小如何影响镜像拉取耗时；
6. 如何导出镜像拉取耗时和网络传输结果。

## 实验设计

样例依次部署三个函数：

```text
image-pull-small-cold   使用 small 镜像，首次部署，触发 docker_pull
image-pull-small-warm   使用同一个 small 镜像，同节点部署，复用镜像缓存
image-pull-large-cold   使用 large 镜像，首次部署，触发更大的 docker_pull
```

为了稳定观察缓存复用，样例使用 `FixedNodeScheduler` 将函数副本固定部署到同一节点。

## 输出文件

运行结束后，结果会保存到：

```text
examples/image_pull_network/outputs/
```

主要包括：

```text
image_pull_probe.csv
image_pull_summary.csv
flow.csv
image_pull_flow_summary.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
invocations.csv
```

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 初始化 Docker Registry；
3. 注册 small / large 函数镜像；
4. 顺序部署三个函数；
5. 固定调度到同一节点；
6. 运行仿真；
7. 导出镜像拉取和网络流指标。

### `scheduler.py`

固定节点调度器文件。

该文件提供：

```text
FixedNodeScheduler
```

它优先选择 `server_0`，用于保证多个函数副本部署到同一节点，从而稳定观察节点镜像缓存复用。

### `simulator.py`

镜像拉取观测模拟器文件。

该文件提供：

```text
ImagePullSimulatorFactory
ImagePullFunctionSimulator
```

其核心逻辑是在 `deploy()` 中调用 `docker.pull()`，并记录 `image_pull_probe` 指标。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `image_pull_probe`、`flow`、`schedule`、`replica_deployment` 等指标，并生成摘要结果。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
