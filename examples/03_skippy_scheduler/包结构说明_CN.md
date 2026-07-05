# skippy_scheduler 包结构说明

`skippy_scheduler` 是 faas-sim 原生 Skippy 调度机制样例包，用于演示默认调度器如何完成资源过滤、节点选择和调度结果输出。

## 目录结构

```text
skippy_scheduler/
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
2. 注册函数镜像；
3. 构造不同资源请求的函数部署；
4. 创建 `Simulation`；
5. 替换为可观测 Skippy 调度器；
6. 运行请求负载；
7. 导出调度结果指标。

### `scheduler.py`

可观测 Skippy 调度器文件。

该文件提供：

```text
InstrumentedSkippyScheduler
```

它继承 Skippy 原生 `Scheduler`，保留默认调度语义，只额外记录候选节点、可行节点和调度结果。

### `simulator.py`

函数执行模拟器文件。

该文件提供稳定函数执行时间，保证样例重点集中在调度结果，而不是执行模型差异。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `skippy_scheduler_result`、`skippy_scheduler_candidate`、`schedule` 等 DataFrame，并生成调度摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。

## 运行命令

在 faas-sim 项目根目录执行：

```bash
python -u examples/skippy_scheduler/main.py
```

## 样例定位

该样例属于“原生 faas-sim 功能样例”。

它用于补齐官方 examples 中没有系统展示的 Skippy 默认调度机制，为后续实现缓存状态感知调度器提供 baseline。
