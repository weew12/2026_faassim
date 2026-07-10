# 指标与日志：`sim/metrics.py`、`sim/logging.py`

## 1. 模块定位

这两个模块分成上下两层：

- `Metrics` 理解 FaaS 业务语义，知道部署、调度、调用、网络和资源分别应记录哪些字段；
- `RuntimeLogger` 只负责把 measurement、fields、tags 和时间组成通用记录。

```text
业务模块 -> Metrics.log_xxx() -> RuntimeLogger.log() -> Record -> 内存/控制台/其他后端
```

## 2. 时间源

### `Clock`

定义 `now()` 协议，使日志系统不依赖固定时间实现。

### `WallClock`

返回真实世界当前时间，适合普通运行日志。

### `SimulatedClock`

将 `env.now` 的仿真秒数加到指定起始 `datetime` 上。这样 DataFrame 可以使用日期时间索引，同时仍保持离散事件时间语义。

```text
record_time = simulation_start_datetime + env.now seconds
```

仿真结果比较应优先使用仿真时间，不应受程序真实运行速度影响。

## 3. `Record`

`Record` 是不可变命名元组，概念字段包括：

- measurement：指标类别；
- time：记录时间；
- fields：待分析的数值或业务值；
- tags：用于筛选和分组的维度。

例如一次网络流可表示为：

```text
measurement = flow
fields      = {bytes: ..., duration: ...}
tags        = {source: ..., sink: ..., action_type: docker_pull}
```

## 4. `RuntimeLogger`

### `log(metric, value, time=None, **tags)`

将值规范化为 fields，补充时间与 tags，再调用 `_store_record()`。调用者可以传单值或字段字典。

### `get(name, **tags)`

返回预绑定 measurement 和 tags 的日志函数，适合把日志回调交给其他组件。

### `_store_record(record)`

后端扩展点。默认 logger 保存记录，子类可以改成打印、丢弃或持久化。

## 5. 日志后端

### `NullLogger`

忽略所有日志，用于不需要记录的性能测试。它会降低内存占用，但之后无法生成指标表。

### `PrintLogger`

把 Record 输出到控制台，适合调试小实验。大规模请求下会产生大量输出，并显著拖慢墙上执行时间。

需要 CSV、数据库或时序数据库时，应实现新的 `_store_record()`，而不是把文件写入散落到所有业务模块。

## 6. `Metrics` 的内部状态

除结构化日志外，`Metrics` 还维护控制逻辑需要的轻量计数：

- 每个函数累计调用数 `invocations`；
- 全局调用数 `total_invocations`；
- 每个函数最后调用时间 `last_invocation`。

这些值被自动伸缩器和 `faas_idler` 使用，因此 `log_start_exec()` 不只是输出日志，也会影响控制决策。

## 7. 指标类别

### 部署与定义

- `log_function_deployment()`；
- `log_function_definition()`；
- `log_function_replica()`；
- `log_function_deployment_lifecycle()`。

### 调度

- `log_queue_schedule()`：进入队列；
- `log_start_schedule()`：调度开始；
- `log_finish_schedule()`：调度结束及是否成功。

三类事件通过 `replica_id` 关联，可计算排队和调度耗时。

### 副本启动生命周期

- `log_deploy()`；
- `log_startup()`；
- `log_setup()`；
- `log_finish_deploy()`；
- `log_teardown()`。

### 请求执行

- `log_start_exec()` / `log_stop_exec()`：执行钩子；
- `log_invocation()`：端到端调用字段；
- `log_fet()`：函数执行时间窗口。

### 网络

- `log_flow()`：端到端流，记录字节数和持续时间；
- `log_network()`：链路级字节数和数据类型。

### 资源

- `log_function_resource_utilization()`：副本资源；
- `log_resource_utilization()`：节点聚合资源。

### 伸缩

- `log_scaling(function_name, replicas)`：正值表示扩容，负值表示缩容。

## 8. 字段与标签如何选择

一般规则：

- 需要做数值聚合的内容放 fields，如持续时间、字节数、CPU 使用量；
- 用于分组和筛选的内容放 tags，如函数名、节点名、镜像和动作类型；
- 高基数标识（如 request ID）有助于关联，但在外部时序数据库中可能增加索引成本。

同一 measurement 的字段名称和单位必须稳定，否则导出 DataFrame 后会出现难以比较的列。

## 9. `extract_dataframe()`

该方法按 measurement 筛选 Record，把 fields 与 tags 展平为列，并把时间转换成 `DatetimeIndex`。

```python
df = env.metrics.extract_dataframe('invocations')
```

如果没有对应记录，返回空 DataFrame。绘图代码应先判断是否为空，并检查所需列是否存在。

## 10. 当前源码注意点

`Metrics.clock` 属性当前返回 `self.clock`，会递归访问自身；实际底层时钟位于 `self.logger.clock`。源码使用者应避免直接读取该属性，或在后续修复时将其改为返回 logger 的时钟。

## 11. 输出与绘图建议

- 原始 Record 或 DataFrame 应作为事实数据保留；
- 图表由独立分析脚本生成，不要在 `Metrics.log_*` 中绘图；
- 时延分布使用箱线图、ECDF 或分位数曲线，不只报告均值；
- 资源曲线使用仿真时间作横轴，并标出副本伸缩事件；
- 网络图明确字节、MB 或 MiB 单位；
- 多组实验保持 measurement、列名和标签一致。

## 12. 常见误区

- 混用墙上时钟和仿真时钟；
- 同一字段有时记录秒、有时记录毫秒；
- 只记录成功路径，失败请求无法统计；
- 把控制器依赖的 `last_invocation` 更新删除；
- 在高请求量实验中使用 `PrintLogger`；
- 直接访问当前有递归问题的 `Metrics.clock`；
- 先聚合再丢弃请求级记录，导致无法分析尾延迟。

## 13. 阅读检查点

- `Metrics` 与 `RuntimeLogger` 的职责为何分开？
- 哪些指标会反过来影响自动伸缩控制？
- fields 和 tags 应如何划分？
- 如何通过 replica/request 标识关联不同生命周期事件？
