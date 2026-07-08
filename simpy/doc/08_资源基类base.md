# 08 · 资源基类 base

对应源码：`simpy/resources/base.py`

## 1. 文件定位

`base.py` 抽象出所有资源共同的 put/get 请求框架。子类负责定义“什么时候满足请求”，基类负责维护队列和触发循环。

## 2. Put / Get

`Put` 和 `Get` 都是 `Event` 子类。

创建 `Put` 时：

1. 保存所属资源。
2. 记录当前活动进程 `env.active_process`。
3. 加入 `resource.put_queue`。
4. 注册完成回调 `resource._trigger_get`。
5. 立即调用 `resource._trigger_put(None)` 尝试满足。

`Get` 对称：加入 `get_queue`，完成后触发 put 队列重检。

## 3. 为什么请求是事件

因为资源请求可能不能立即满足。例如：

```python
with resource.request() as req:
    yield req
    ...
```

如果槽位已满，`req` 留在队列中，进程挂起；等别人 release 后，`req.succeed()`，进程恢复。

## 4. BaseResource

核心字段：

| 字段 | 含义 |
| --- | --- |
| `_env` | 资源所在仿真环境 |
| `_capacity` | 容量上限，语义由子类解释 |
| `put_queue` | 等待 put 的请求 |
| `get_queue` | 等待 get 的请求 |

核心方法：

- `_do_put(event)`：由子类实现具体规则。
- `_do_get(event)`：由子类实现具体规则。
- `_trigger_put(get_event)`：遍历 put 队列尝试满足请求。
- `_trigger_get(put_event)`：遍历 get 队列尝试满足请求。

## 5. 队列不变量

`_trigger_put` 和 `_trigger_get` 都维护一个重要不变量：队列中只能保留尚未触发的请求。

如果子类在 `_do_put` 或 `_do_get` 中错误修改队列，基类会抛出：

```text
Put queue invariant violated
Get queue invariant violated
```

## 6. 子类如何扩展

子类只需要回答两个问题：

1. 当前状态下请求能否满足？
2. 满足时如何更新资源状态并调用 `event.succeed(value)`？

例如 `Container._do_get` 就是：水位足够则减少水位并成功，否则保持排队。

