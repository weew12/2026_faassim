# 01 · simpy 包入口

> 对应源码：`simpy/__init__.py`（110 行）

## 1. 职责

`simpy/__init__.py` 是 faas-sim 内置 SimPy 子包的**聚合入口**。它本身不实现任何仿真
逻辑，只做两件事：

1. 从 `core` / `events` / `exceptions` / `rt` / `resources.{container,resource,store}`
   等子模块 `import` 出需要对外暴露的类。
2. 通过 `__all__` 显式声明公开对象清单，并基于该清单自动生成 Sphinx autosummary
   风格的目录文本，注入到模块 docstring 中。

这样调用方使用 `import simpy` 之后，可以像使用 pip 安装的 `simpy==3.0.11` 一样直接
访问 `Environment` / `Timeout` / `Resource` / `Container` / `Store` 等对象，无需关心
它们在包内的具体文件分布。

## 2. 版本说明

```python
try:
    __version__ = importlib.metadata.version('simpy')
except importlib.metadata.PackageNotFoundError:
    __version__ = 'embedded'
```

- 如果当前环境已经通过 pip 安装了 simpy 发行包，则 `__version__` 取自 metadata。
- 否则（faas-sim 当前用法：源码内置、未作为发行包安装），固定为字符串 `'embedded'`，
  表示这是内置源码版本。

## 3. `__all__` 清单（17 个对象）

按 `__init__.py` 的字母序列出，每个对象都能在 `simpy.<对象>` 直接取到：

| `__all__` 顺序 | 对象 | 来源文件 |
| ------------- | ---- | -------- |
| 1  | `AllOf` | `events.py` |
| 2  | `AnyOf` | `events.py` |
| 3  | `Container` | `resources/container.py` |
| 4  | `Environment` | `core.py` |
| 5  | `Event` | `events.py` |
| 6  | `FilterStore` | `resources/store.py` |
| 7  | `Interrupt` | `exceptions.py` |
| 8  | `PreemptiveResource` | `resources/resource.py` |
| 9  | `PriorityItem` | `resources/store.py` |
| 10 | `PriorityResource` | `resources/resource.py` |
| 11 | `PriorityStore` | `resources/store.py` |
| 12 | `Process` | `events.py` |
| 13 | `RealtimeEnvironment` | `rt.py` |
| 14 | `Resource` | `resources/resource.py` |
| 15 | `SimPyException` | `exceptions.py` |
| 16 | `Store` | `resources/store.py` |
| 17 | `Timeout` | `events.py` |

## 4. 内部组织（按类别）

### 4.1 Environments（仿真环境）

- `Environment` —— 见 `02_核心引擎core.md`
- `RealtimeEnvironment` —— 见 `05_实时仿真rt.md`

### 4.2 Events（事件与进程）

- `Event` / `Timeout` / `Process`
- `AllOf` / `AnyOf`（基于 `Condition`）
- `Interrupt`（同时归入 Exceptions）

详见 `03_事件与进程events.md` 与 `04_异常体系exceptions.md`。

### 4.3 Resources（共享资源）

- `Resource` / `PriorityResource` / `PreemptiveResource` —— 见 `10_槽位资源resource.md`
- `Container` —— 见 `09_容器资源container.md`
- `Store` / `PriorityStore` / `FilterStore` / `PriorityItem` —— 见 `11_对象存储store.md`
- 通用 put/get 框架 —— 见 `08_资源基类base.md`

### 4.4 Exceptions（异常）

- `SimPyException` / `Interrupt` —— 见 `04_异常体系exceptions.md`

## 5. 自动目录生成（`_compile_toc` / `_toc`）

模块 docstring 末尾通过 `_compile_toc(_toc)` 自动嵌入一份 Sphinx autosummary 风格的
目录文本，分四节：

```
Environments  : Environment, RealtimeEnvironment
Events        : Event, Timeout, Process, AllOf, AnyOf, Interrupt
Resources     : Resource, PriorityResource, PreemptiveResource, Container,
                Store, PriorityItem, PriorityStore, FilterStore
Exceptions    : SimPyException, Interrupt
```

并且通过 `assert set(__all__) == {obj.__name__ for _, objs in _toc for obj in objs}`
保证 `__all__` 与 `_toc` 中的对象名严格一致——一旦列表中漏了某个对象或拼错了名字，
启动时就会立刻报错。

## 6. faas-sim 中的使用约定

faas-sim 默认通过 `from simpy import Environment, ...` 拿到这些对象，并在
`sim.core.Environment` 中继承扩展。模块层面的 import 兼容以下两种写法：

```python
import simpy
env = simpy.Environment()           # ✅
env.timeout(1.0)                    # ✅ 等价于 simpy.Timeout(env, 1.0)

from simpy import Environment, Timeout
env = Environment()
env.timeout(1.0)                    # ✅
```

无论写法如何，最终拿到的都是同一个 `Environment` 类，因此 faas-sim 的任何调用方都
可以无感切换。
