# 性能退化模型：`sim/degradation.py`

## 1. 模块定位

性能退化描述多个函数在同一节点并发时，由 CPU、I/O、GPU、网络和内存竞争造成的执行时间变化。

`sim/degradation.py` 不训练模型，也不直接延长请求时间；它只把当前并发调用整理成固定顺序的 NumPy 特征向量，交给节点级模型预测。

```text
节点当前/历史 calls
  + ResourceOracle 资源画像
  + 时间窗口
  + 节点内存容量
        |
        v
create_degradation_model_input
        |
        v
固定长度 ndarray
        |
        v
NodeState 中的退化模型预测
```

## 2. `create_degradation_model_input()` 参数

| 参数 | 含义 |
|---|---|
| `calls` | 可能与目标执行窗口重叠的调用集合 |
| `start_ts` | 目标时间窗口开始 |
| `end_ts` | 目标时间窗口结束 |
| `node_name` | 目标节点名称 |
| `ram_capacity` | 节点总内存容量 |
| `resource_oracle` | 按节点和函数查询资源画像 |

调用集合为空时直接返回空数组，调用方应把它解释为无并发干扰，而不是有效模型输入。

## 3. 时间重叠计算

每个调用对窗口的有效重叠时间为：

```text
overlap_start = max(start_ts, call.start)
overlap_end   = min(end_ts, call.end or end_ts)
overlap       = overlap_end - overlap_start
```

资源贡献近似为：

```text
weighted_resource = overlap * resource_characterization[resource]
```

这相当于用“资源强度乘持续时间”表达窗口内压力。调用方应事先过滤完全不重叠的请求，否则可能产生负 overlap。

## 4. 按 Pod 聚合

资源先按 `pod_name` 聚合，维度包括：

- `cpu`；
- `gpu`；
- `blkio`；
- `net`。

内存单独处理：同一 Pod 只累计一次容器内存请求，避免同副本多个并发调用重复计算常驻内存。

## 5. 特征向量结构

对四类资源分别计算七个统计量：

```text
mean, std, min, max, p25, p50, p75
```

随后追加：

1. Pod 数量；
2. 四类资源总和；
3. `ram / ram_capacity`。

理论特征总长度为：

```text
4 resources * 7 statistics + 1 pod count + 4 sums + 1 RAM ratio = 34
```

模型训练和推理必须使用完全相同的特征顺序、统计定义和归一化方法。

## 6. NaN 处理

统计值为 NaN 时转换为 `0`，使输出保持数值数组。但这会把“没有有效样本”和“真实统计值为零”合并，模型数据准备时应确认这种编码符合训练过程。

## 7. 与 `NodeState` 的关系

`NodeState` 保存节点退化模型及缓存。典型流程是：

```text
具体 simulator 确定基础执行时间
  -> 收集节点并发请求
  -> 构造 degradation input
  -> 节点模型预测放大系数
  -> adjusted_duration = base_duration * factor
  -> yield env.timeout(adjusted_duration)
```

同一节点状态下重复预测可使用缓存，但并发请求变化后必须避免错误复用旧值。

## 8. 当前源码中的两个关键问题

### 8.1 资源画像存在性判断相反

当前代码在 `call_resources` 为真时抛出“Can't find resources”，随后又在假值路径尝试下标读取资源。这与错误信息和后续使用逻辑相反。按预期应在资源画像为空或 `None` 时处理缺失。

### 8.2 NumPy 百分位参数口径

`np.percentile` 的 `q` 使用 `0` 到 `100` 的百分数。当前代码传入 `0.25`、`0.5`、`0.75`，实际是第 0.25、0.5、0.75 百分位，不是命名所暗示的第 25、50、75 百分位。若训练模型使用真正四分位数，应传入 `25`、`50`、`75`，并同步重训或确认模型特征。

这两点会直接影响模型输入正确性，在启用退化实验前应优先修复并增加测试。

## 9. 建议测试

至少覆盖：

1. 空调用集合返回空数组；
2. 单调用完整覆盖窗口；
3. 调用只与窗口部分重叠；
4. 未结束调用使用 `end_ts`；
5. 同一 Pod 多调用只计一次内存；
6. 多 Pod 聚合得到固定 34 维；
7. 缺少资源画像时行为明确；
8. 四分位数与手工计算一致；
9. `ram_capacity == 0` 被拒绝；
10. 完全不重叠调用不会产生负贡献。

## 10. 常见误区

- 把退化模型输入当成实时资源账本；
- 训练和推理的特征顺序不同；
- 使用毫秒训练、秒推理；
- 并发集合包含不重叠请求；
- 对每个请求重复累计 Pod 常驻内存；
- 修正特征定义后继续使用旧模型文件；
- 随机或回归模型输出负放大系数却不做边界处理。

## 11. 阅读检查点

- 资源强度为什么要乘时间重叠长度？
- 为什么内存按 Pod 去重？
- 当前特征向量为何是 34 维？
- 修改百分位定义后为什么可能需要重新训练模型？
