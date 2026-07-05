# image_pull_network：faas-sim 镜像拉取网络样例

本样例用于演示 faas-sim 中 `docker.pull()` 与网络传输之间的关系，重点展示首次镜像拉取、同节点镜像缓存复用以及镜像大小对拉取耗时的影响。

## 运行方式

将 `image_pull_network/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/image_pull_network/main.py
```

## 文件结构

```text
image_pull_network/
├── outputs/
├── __init__.py
├── 包结构说明_CN.md
├── analysis.py
├── main.py
├── README_CN.md
├── scheduler.py
└── simulator.py
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

## 后续扩展

该样例属于原生 faas-sim 功能样例。后续可以在此基础上继续扩展：

1. 不同镜像大小的参数敏感性实验；
2. 不同节点网络位置下的镜像拉取耗时对比；
3. 多函数并发部署导致的镜像拉取竞争；
4. 镜像缓存与函数实例缓存的差异分析；
5. 冷启动阶段 deploy / startup / setup 的拆分建模。
