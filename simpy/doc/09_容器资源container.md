# 09 · 容器资源 container

对应源码：`simpy/resources/container.py`

## 1. 文件定位

`Container` 表示连续容量资源，维护容量上限和当前水位。

- `put(amount)`：增加水位。
- `get(amount)`：减少水位。

请求条件不满足时会排队。

## 2. 核心状态

| 字段 | 含义 |
| --- | --- |
| `_capacity` | 容量上限 |
| `_level` | 当前水位 |
| `put_queue` | 等待剩余空间的 put 请求 |
| `get_queue` | 等待当前水位的 get 请求 |

## 3. 参数校验

构造时：

- `capacity > 0`
- `init >= 0`
- `init <= capacity`

请求时：

- `amount > 0`

这些校验保证水位模型不会出现负数、超过容量或零数量请求。

## 4. put 逻辑

```python
if capacity - level >= amount:
    level += amount
    event.succeed()
```

空间不足时，put 请求留在 `put_queue`。

## 5. get 逻辑

```python
if level >= amount:
    level -= amount
    event.succeed()
```

水位不足时，get 请求留在 `get_queue`。

## 6. 使用示例

```python
def consumer(env, bucket):
    yield bucket.get(3)
    print('got 3 at', env.now)

def producer(env, bucket):
    yield env.timeout(5)
    yield bucket.put(3)

env = simpy.Environment()
bucket = simpy.Container(env, capacity=10, init=0)
env.process(consumer(env, bucket))
env.process(producer(env, bucket))
env.run()
```

consumer 会在 `bucket.get(3)` 上等待，直到 producer 补充水位。

## 7. faas-sim 可用场景

- 缓存容量
- 令牌桶限流
- 能量/预算消耗
- 可累计资源的生产与消费

