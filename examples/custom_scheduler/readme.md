# examples/custom_scheduler

本示例演示如何替换 faas-sim 默认调度器，并通过自定义 `schedule(pod)` 方法控制函数副本放置。

## 运行方式

在项目根目录执行：

```bash
python -u examples/custom_scheduler/main.py
```

## 示例目标

- 复用 `examples.basic` 的拓扑和 benchmark。
- 通过 `sim.create_scheduler = CustomScheduler.create` 接入自定义调度器。
- 在 `schedule(pod)` 中读取 `ClusterContext` 的节点列表。
- 随机选择一个节点并返回 `SchedulingResult`。

## 文件说明

- `main.py`：自定义调度器、调度器工厂和运行入口。
- `__init__.py`：包说明。

## 调度流程

1. `Simulation` 初始化 FaaS 系统时调用 `CustomScheduler.create(env)`。
2. `CustomScheduler` 保存 `env.cluster` 作为集群上下文。
3. 每次需要部署函数副本时，平台调用 `schedule(pod)`。
4. 示例调度器从 `cluster.list_nodes()` 中随机选一个节点。
5. 调度器返回 `SchedulingResult(node, len(nodes), [])`。

该策略只用于演示接口。实际实验中可以在 `schedule` 中加入资源、架构、镜像缓存、数据位置或网络延迟等约束。
