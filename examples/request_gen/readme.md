# examples/request_gen

本示例演示如何使用 `sim.requestgen` 生成函数调用请求，并把请求流接入 faas-sim 的 benchmark。

## 运行方式

在项目根目录执行：

```bash
python -u examples/request_gen/main.py
```

## 示例目标

- 部署一个 `python-pi` 函数。
- 使用固定平均速率 `20 RPS` 生成请求强度。
- 使用指数分布到达间隔模拟随机请求流。
- 通过 `function_trigger` 自动触发最多 `100` 次函数调用。

## 文件说明

- `main.py`：示例入口，定义拓扑、benchmark、函数部署和请求生成逻辑。
- `__init__.py`：包说明。

## 请求生成流程

1. `constant_rps_profile(rps=20)` 持续产生固定平均请求速率。
2. `expovariate_arrival_profile(...)` 将 RPS 转换为指数分布的 inter-arrival time。
3. `function_trigger(env, deployment, ia_generator, max_requests=100)` 按到达间隔触发 `env.faas.invoke(...)`。

这相当于为 `python-pi` 函数构造一个平均 20 RPS、最多 100 个请求的随机到达工作负载。
