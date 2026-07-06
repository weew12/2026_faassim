# 02_load_balancer：faas-sim 原生负载均衡样例

本样例用于演示 faas-sim 的原生负载均衡能力，重点展示多个函数副本存在时，请求如何被路由到具体副本。

## 运行方式

将 `02_load_balancer/` 放入项目的 `examples/` 目录后，在项目根目录运行：

```bash
python -u examples/02_load_balancer/main.py
```

## 样例目标

该样例主要回答以下问题：

1. faas-sim 中负载均衡器在什么情况下被调用；
2. 多个 RUNNING 副本存在时，请求如何选择目标副本；
3. 如何替换 `DefaultFaasSystem.load_balancer`；
4. 如何记录每次请求路由决策；
5. 如何导出 `load_balancer.csv`；
6. 如何统计请求在副本之间的分布。

## 输出文件

运行结束后，结果会保存到：

```text
examples/02_load_balancer/outputs/
```

主要包括：

```text
load_balancer.csv                     # 每次路由决策原始记录
load_balancer_routing_sequence.csv    # 按 request_id 排序的路由序列（论文 demo 关键图）
load_balancer_summary.csv             # 增强版摘要（含均衡度指标）
load_balancer_replica_distribution.csv # 每个 replica 路由次数分布
invocations.csv
schedule.csv
function_deployments.csv
function_deployment_lifecycle.csv
function_replicas.csv
replica_deployment.csv
flow.csv
```

### 论文 demo 关键图说明

`load_balancer_routing_sequence.csv` 是本样例的核心导出。其列含义：

- `request_id`：请求 ID（1..N）
- `replica_index`：被选中的 replica 索引（轮询 LB 严格按 0/1/2/0/1/2 顺序）
- `selected_replica_id`：replica 对象 ID
- `selected_node`：被选中的节点

画图直接用：

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("outputs/load_balancer_routing_sequence.csv")
plt.figure(figsize=(10, 4))
plt.step(df.request_id, df.replica_index, where="post")
plt.xlabel("Request ID (sequence)")
plt.ylabel("Replica Index (round-robin target)")
plt.title("Round-robin load balancing: 3 replicas served 30 requests")
plt.yticks([0, 1, 2])
plt.grid(True, alpha=0.3)
plt.show()
```

### summary 增强字段

`load_balancer_summary.csv` 新增 4 个均衡度指标：

- `max_routed_requests` / `min_routed_requests`：每个 replica 路由次数的最大/最小值
- `balance_std`：路由次数的总体标准差（越小越均衡）
- `balance_ratio`：min/max（越接近 1 越均衡）
- `max_consecutive_same_replica`：同一 replica 连续被路由的最大次数（严格轮询时为 1）

## 文件说明

### `main.py`

样例主入口。

职责包括：

1. 创建拓扑；
2. 注册函数镜像；
3. 构造拥有 3 个副本的 `FunctionDeployment`；
4. 创建 `Simulation`；
5. 启用可观测轮询负载均衡器；
6. 触发请求负载；
7. 导出负载均衡结果指标。

### `load_balancer.py`

负载均衡策略文件。

该文件提供：

```text
InstrumentedRoundRobinLoadBalancer
```

它保持轮询负载均衡语义，同时把每次请求路由决策写入 `load_balancer` 指标。

### `system.py`

FaaS 系统创建文件。

该文件提供 `create_load_balancer_faas_system(env)`，用于创建 `DefaultFaasSystem` 并替换其 `load_balancer` 字段。

### `simulator.py`

函数执行模拟器文件。

该文件提供稳定函数执行时间，便于观察请求路由分布，而不是把实验差异混入执行模型。

### `analysis.py`

指标导出与分析文件。

该文件负责导出 `load_balancer`、`invocations`、`schedule` 等 DataFrame，并生成路由摘要。

### `outputs/`

运行输出目录。

用于保存 CSV 结果文件。
