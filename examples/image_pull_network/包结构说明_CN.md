# image_pull_network 包结构说明

`image_pull_network` 是 faas-sim 镜像拉取网络样例包，用于演示 `docker.pull()`、网络 Flow 和节点镜像缓存之间的关系。

## 目录结构

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

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/image_pull_network/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有单独展示的镜像拉取网络过程，为后续冷启动建模和镜像缓存实验提供基础。
