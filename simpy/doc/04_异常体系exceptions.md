# 04 · 异常体系 exceptions

> 对应源码：`simpy/exceptions.py`（36 行）

## 1. 职责

`exceptions.py` 定义 SimPy 运行时使用的基础异常。规模虽小，但有两个关键点：

- `Interrupt` —— 进程被中断的统一入口。被中断时，`Process._resume` 会把该异常作为
  `throw` 注入生成器，业务进程可捕获后执行清理或重试逻辑。
- `SimPyException` —— SimPy 异常的基类。所有仿真框架自身抛出的异常都可被它统一捕获。

## 2. 类层次

```
Exception
└── SimPyException         # SimPy 异常的共同基类
    └── Interrupt          # 进程中断专用异常
```

## 3. `SimPyException`

```python
class SimPyException(Exception):
    """SimPy 异常基类，用于表示由仿真框架自身产生的异常。"""
```

- 直接继承自 `Exception`。
- 业务层可以用 `except SimPyException:` 一次性捕获所有 SimPy 内部异常。
- 在 faas-sim 中常用于隔离仿真内部错误和用户业务异常。

## 4. `Interrupt`

```python
class Interrupt(SimPyException):
    def __init__(self, cause: Optional[Any]):
        super().__init__(cause)

    def __str__(self):
        return f'{self.__class__.__name__}({self.cause!r})'

    @property
    def cause(self) -> Optional[Any]:
        return self.args[0]
```

### 4.1 构造

- 接收一个 `cause`（任意业务对象），写入 `args[0]`。
- `cause` 通常携带中断原因：
  - `PreemptiveResource` 抢占时传入 `Preempted(by=..., usage_since=..., resource=...)`
    对象
  - `util.subscribe_at` 在订阅事件触发时传入 `(signaller, result)` 元组
  - 业务层取消副本时传入自定义对象

### 4.2 `cause` 属性

- `@property` 形式返回 `self.args[0]`，因此业务进程可以 `except Interrupt as i: i.cause`
  拿到原始原因对象。

### 4.3 `__str__`

- 返回 `Interrupt(<cause repr>)`，便于日志和断点调试。

## 5. 触发路径

`Interrupt` 不由用户直接 `raise`，而是通过以下两条路径产生：

1. **`Process.interrupt(cause)`**：`Process` 内部构造 `Interruption(process, cause)`，
   环境 step 时回调里通过 `process._resume` 把 `Interrupt(cause)` 作为 `throw` 注入
   生成器（详见 `03_事件与进程events.md` 的 `Process._resume` 与 `Interruption`）。

2. **`util.subscribe_at(event)`**：订阅进程在被订阅事件触发时被中断（详见
   `06_工具函数util.md`）。

## 6. 业务进程的典型处理

```python
def worker(env):
    try:
        yield env.timeout(100)
    except simpy.Interrupt as i:
        print('worker interrupted:', i.cause)
        # 执行清理、释放资源等
```

如果不捕获 `Interrupt`，异常会沿生成器一路冒泡到 `Process._resume`，最终导致
`Process` 事件失败，并通过 `Environment.step()` 抛出（详见
`02_核心引擎core.md` 第 5.5 节）。

## 7. faas-sim 中的使用场景

| 场景 | 谁触发 | cause |
| ---- | ------ | ----- |
| 抢占式资源剥夺 | `PreemptiveResource._do_put` | `Preempted(by=..., usage_since=..., resource=...)` |
| 外部取消副本 | faas-sim 调度器 | 自定义字符串或对象 |
| 自动伸缩时回收 | 伸缩器 | `'scaled_in'` 等字符串 |
| 订阅其他事件 | `util.subscribe_at` | `(signaller, result)` 元组 |
