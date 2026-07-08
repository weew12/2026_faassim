# 04 · 异常体系 exceptions

对应源码：`simpy/exceptions.py`

## 1. 文件定位

该文件很小，只定义两个异常：

- `SimPyException`
- `Interrupt`

其中 `Interrupt` 是源码阅读重点。

## 2. SimPyException

`SimPyException` 是 SimPy 内部异常的基类。业务代码可以用它区分“仿真框架异常”和普通 Python 异常。

## 3. Interrupt

`Interrupt` 表示进程被外部中断。它不是普通函数调用抛出的异常，而是由事件系统通过 `Process._resume()` 注入生成器：

```python
try:
    yield env.timeout(10)
except simpy.Interrupt as intr:
    print(intr.cause)
```

`cause` 可以是任意对象。常见来源：

| 来源 | cause |
| --- | --- |
| `Process.interrupt(cause)` | 调用方传入的对象 |
| `PreemptiveResource` 抢占 | `Preempted(...)` |
| `subscribe_at(event)` | `(event, result)` |

## 4. 为什么 cause 放在 args[0]

`Interrupt.__init__()` 调用 `super().__init__(cause)`，因此 cause 保存在标准异常的 `args[0]` 中。`cause` 属性只是一个更清晰的读取入口。

## 5. 阅读关联

- 中断事件创建：`events.py::Interruption.__init__`
- 中断注入：`events.py::Interruption._interrupt`
- 抢占场景：`resources/resource.py::PreemptiveResource`
- 订阅场景：`util.py::subscribe_at`

