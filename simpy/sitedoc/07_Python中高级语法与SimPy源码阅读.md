# 07. Python 中高级语法与 SimPy 源码阅读

这份文档面向“读懂 SimPy 源码”，不是泛泛的 Python 教程。组织顺序是先简单、后复杂：先讲类、模块、属性、异常，再讲生成器、上下文管理器、回调、堆队列、类型系统、描述符和运算符重载。

读完后，应能通读这些文件：

- `simpy/core.py`
- `simpy/events.py`
- `simpy/exceptions.py`
- `simpy/util.py`
- `simpy/rt.py`
- `simpy/resources/base.py`
- `simpy/resources/resource.py`
- `simpy/resources/container.py`
- `simpy/resources/store.py`

## 0. 总体阅读路线

SimPy 源码的核心句子是：

```python
def process(env, resource):
    with resource.request() as req:
        yield req
```

这两行同时涉及：

- 类和对象：`request()` 返回一个请求事件对象。
- 上下文管理器：`with` 进入和退出时自动清理请求。
- 生成器：`yield req` 暂停当前进程。
- 回调：请求事件完成后恢复等待它的进程。
- 异常：进程被中断时在 `yield` 处收到 `Interrupt`。
- 动态绑定：`resource.request()` 实际由 `BoundClass` 绑定请求类得到。

如果你只掌握了变量、函数、列表、字典、`if`、`for`、普通类这些基础语法，不需要先去补完整本 Python 高级教程。读 SimPy 最需要建立三个核心直觉：

1. Python 函数和类本身也是对象，可以被保存、传递和动态绑定。
2. 生成器不是普通函数，它可以暂停，并且之后从暂停处继续执行。
3. SimPy 的“等待”不是线程阻塞，而是把“恢复我”的函数放进事件回调列表，等环境以后调用。

后面的每一节都会尽量用“普通 Python 写法 -> SimPy 源码写法 -> 你该怎么读”这个顺序解释。

推荐学习顺序：

1. 模块、包和导入。
2. 类、对象、继承、`super()`。
3. 属性方法 `@property`、类变量、私有约定。
4. 异常和自定义异常。
5. 生成器、`yield`、`send()`、`throw()`、`StopIteration`。
6. 上下文管理器 `__enter__()` / `__exit__()`。
7. 回调函数和回调列表。
8. `heapq`、排序键、`itertools.count()`。
9. 魔术方法、运算符重载、可迭代协议。
10. 类型标注、泛型、`TYPE_CHECKING`。
11. 描述符、`MethodType`、`BoundClass`。
12. 按文件通读 SimPy 源码。

## 1. 模块、包和导入

### 定义与概念

一个 `.py` 文件就是一个模块。一个目录中包含 `__init__.py` 或作为包使用时，可以组织多个模块。SimPy 把功能拆成多个模块：

初级读者容易混淆“文件路径”和“导入路径”。例如文件在磁盘上是：

```text
simpy/events.py
```

在代码里导入时通常写：

```python
from simpy.events import Event
```

这表示：从 `simpy` 包里的 `events` 模块中导入 `Event` 这个名字。导入后，当前文件就可以直接使用 `Event`。

| 文件 | 作用 |
| --- | --- |
| `core.py` | 仿真环境、事件队列、调度循环 |
| `events.py` | 事件、进程、条件事件、中断事件 |
| `exceptions.py` | SimPy 自定义异常 |
| `resources/base.py` | 资源 put/get 通用框架 |
| `resources/resource.py` | 普通资源、优先级资源、抢占资源 |
| `resources/container.py` | 连续容量资源 |
| `resources/store.py` | 对象队列资源 |
| `rt.py` | 实时仿真环境 |
| `util.py` | 工具函数 |

### 语法

```python
from simpy.events import Event, Timeout
from simpy.core import Environment
```

常见导入形式有三种：

```python
import simpy
```

这种写法导入整个包，使用时要写 `simpy.Environment`。

```python
from simpy import Environment
```

这种写法只把 `Environment` 这个名字导入当前文件，使用时直接写 `Environment`。

```python
from simpy.events import Event as SimPyEvent
```

这种写法导入时改名，适合避免名字冲突。

### SimPy 场景

`core.py` 需要创建事件，所以导入：

```python
from simpy.events import Event, Process, Timeout, AllOf, AnyOf
```

`events.py` 需要中断异常，所以导入：

```python
from simpy.exceptions import Interrupt
```

### 最小实战

```python
# shapes.py
class Circle:
    pass


# main.py
from shapes import Circle

obj = Circle()
print(type(obj).__name__)
```

### 阅读提示

看源码时先看 import，可以知道模块依赖方向。SimPy 大致是：

```text
exceptions.py -> events.py -> core.py -> resources/*.py
```

读源码时可以按这个步骤处理 import：

1. 先分清标准库、第三方库、本项目模块。
2. 遇到不认识的名字，先回文件顶部找它从哪里导入。
3. 如果是 `from typing import ...`，大多是类型标注，不一定影响运行逻辑。
4. 如果两个模块互相引用，注意是否放在 `TYPE_CHECKING` 里；这通常是为了避免循环导入。

## 2. 类、对象和实例属性

### 定义与概念

类定义对象的结构和行为；对象是类的实例。SimPy 中几乎所有核心概念都是类：

- `Environment`
- `Event`
- `Timeout`
- `Process`
- `Resource`
- `Container`
- `Store`

可以把类理解成“模板”，对象理解成“按模板造出来的一件具体东西”。例如 `Event` 是事件模板，`env.timeout(5)` 创建出来的是一个具体事件对象。

`__init__()` 是对象创建后的初始化方法。你看到：

```python
event = Event(env)
```

Python 内部大致做了两件事：

1. 创建一个空的 `Event` 对象。
2. 自动调用 `Event.__init__(event, env)` 初始化它。

所以 `__init__()` 的第一个参数 `self`，就是刚创建出来的那个对象。

### 语法

```python
class Event:
    def __init__(self, env):
        self.env = env
        self.callbacks = []
```

`self` 表示当前对象。`self.env`、`self.callbacks` 是实例属性。

可以把 `self.env = env` 理解成：给当前对象贴一个名为 `env` 的标签，标签里保存传进来的环境对象。

```python
event.env
```

之后就能通过这个标签拿到环境。

### SimPy 场景

`Event.__init__()` 中保存事件所属环境和回调列表：

```python
self.env = env
self.callbacks = []
```

这说明每个事件都知道：

- 自己属于哪个 `Environment`。
- 自己被处理时要调用哪些回调。

### 最小实战

```python
class Task:
    def __init__(self, name):
        self.name = name
        self.done = False

    def finish(self):
        self.done = True


task = Task("load-image")
task.finish()
print(task.name, task.done)
```

再看一个更接近 SimPy 的版本：

```python
class Event:
    def __init__(self, env):
        self.env = env
        self.callbacks = []
        self._value = None


class Environment:
    pass


env = Environment()
event = Event(env)

print(event.env is env)
print(event.callbacks)
```

这里的 `event.env is env` 为 `True`，说明事件保存的是同一个环境对象的引用，不是复制了一份环境。

### 阅读提示

读一个类时，先找：

- `__init__()`：对象有哪些核心字段。
- 普通方法：对象能做什么。
- `@property`：对象暴露了哪些计算状态。
- 父类：它复用了谁的逻辑。

读 SimPy 类时，还要特别注意“字段什么时候出现”。有些字段不是在 `__init__()` 中声明，而是在某个方法中第一次赋值。例如 `Event._ok` 可能在 `succeed()` 或 `fail()` 时才出现。Python 允许这样动态添加实例属性，这和 Java/C++ 这类语言很不一样。

## 3. 继承和 super()

### 定义与概念

继承表示一个类复用另一个类。子类可以新增方法，也可以覆盖父类方法。`super()` 用于调用父类实现。

初级读者可以先用“更具体的一种”来理解继承：

- `Timeout` 是更具体的 `Event`。
- `Process` 是更具体的 `Event`。
- `PriorityResource` 是更具体的 `Resource`。
- `PreemptiveResource` 是更具体的 `PriorityResource`。

子类对象可以使用父类方法。比如 `Timeout` 继承 `Event` 后，如果没有重写 `succeed()`，就能直接使用 `Event.succeed()`。

### 语法

```python
class Child(Parent):
    def __init__(self):
        super().__init__()
```

如果不用 `super()`，也可以显式写父类名：

```python
Parent.__init__(self)
```

但在现代 Python 中，更推荐 `super().__init__()`。它对多层继承和多重继承更稳。

### SimPy 场景

`Timeout` 是一种事件：

```python
class Timeout(Event):
    ...
```

`PriorityResource` 是一种资源：

```python
class PriorityResource(Resource):
    ...
```

`PreemptiveResource` 是一种优先级资源：

```python
class PreemptiveResource(PriorityResource):
    ...
```

抢占资源先做抢占判断，再复用普通资源占用逻辑：

```python
def _do_put(self, event):
    return super()._do_put(event)
```

### 最小实战

```python
class Event:
    def __init__(self):
        self.callbacks = []

    def succeed(self):
        print("event succeeded")


class Timeout(Event):
    def __init__(self, delay):
        super().__init__()
        self.delay = delay


timeout = Timeout(5)
timeout.succeed()
print(timeout.delay)
```

执行顺序是：

1. `Timeout(5)` 创建 `Timeout` 对象。
2. 进入 `Timeout.__init__()`。
3. `super().__init__()` 调用 `Event.__init__()`，创建 `callbacks`。
4. 回到 `Timeout.__init__()`，设置 `delay`。
5. `timeout.succeed()` 在 `Timeout` 中找不到，于是去父类 `Event` 找。

### 阅读提示

看到 `super()` 时，要问：

- 子类是在父类前面加逻辑，还是后面加逻辑？
- 子类有没有改变父类依赖的字段？
- 子类返回值是否遵守父类约定？

SimPy 有些地方为了性能没有调用 `super().__init__()`，而是手动写了父类初始化中的关键字段。例如 `Timeout` 会直接设置 `self.env`、`self.callbacks`、`self._value`。读到这种代码时不要惊讶，它是在减少事件创建开销，但你仍然可以按“它做了 Event 初始化该做的事”来理解。

## 4. 类变量、实例变量和 ClassVar

### 定义与概念

类变量属于类，实例变量属于对象。类变量常用于配置子类行为。

区别可以这样记：

- 写在类缩进下、方法外面的，通常是类变量。
- 写成 `self.xxx = ...` 的，通常是实例变量。

类变量会被所有实例共享；实例变量每个对象各有一份。

### 语法

```python
class Base:
    QueueType = list

    def __init__(self):
        self.queue = self.QueueType()
```

类型标注中，`ClassVar` 表示这是类变量：

```python
from typing import ClassVar

class A:
    value: ClassVar[int] = 1
```

一个容易踩坑的例子：

```python
class Bad:
    items = []


a = Bad()
b = Bad()
a.items.append("x")
print(b.items)
```

输出中 `b.items` 也能看到 `"x"`，因为 `items` 是类变量，被两个实例共享。

如果希望每个对象都有自己的列表，应写在 `__init__()` 中：

```python
class Good:
    def __init__(self):
        self.items = []
```

### SimPy 场景

`BaseResource` 默认使用普通列表：

```python
PutQueue = list
GetQueue = list
```

`PriorityResource` 覆盖等待队列类型：

```python
PutQueue = SortedQueue
```

这让优先级资源的请求队列自动排序。

### 最小实战

```python
class BaseQueue:
    QueueType = list

    def __init__(self):
        self.queue = self.QueueType()


class MyQueue(BaseQueue):
    QueueType = list


q = MyQueue()
q.queue.append("job")
print(q.queue)
```

如果子类覆盖类变量：

```python
class SortedQueue(list):
    def append(self, item):
        super().append(item)
        self.sort()


class PriorityQueue(BaseQueue):
    QueueType = SortedQueue


q = PriorityQueue()
q.queue.append(3)
q.queue.append(1)
print(q.queue)
```

这里 `PriorityQueue` 没有重写 `__init__()`，但因为它改了 `QueueType`，父类初始化时创建的队列类型就变了。这正是 `PriorityResource` 使用 `SortedQueue` 的思路。

### 阅读提示

看到类变量时，要检查子类是否覆盖。SimPy 资源系统很多行为就是通过类变量定制的。

## 5. @property 属性方法

### 定义与概念

`@property` 把方法变成属性访问。适合暴露只读状态或计算字段。

普通方法需要加括号：

```python
obj.method()
```

属性方法不加括号：

```python
obj.value
```

但它背后仍然会执行函数。`@property` 的好处是：对外看起来像字段，对内可以动态计算或做校验。

### 语法

```python
class User:
    def __init__(self, first, last):
        self.first = first
        self.last = last

    @property
    def full_name(self):
        return self.first + " " + self.last
```

调用时不加括号：

```python
user.full_name
```

如果要支持赋值，可以再定义 setter：

```python
class Temperature:
    def __init__(self):
        self._celsius = 0

    @property
    def celsius(self):
        return self._celsius

    @celsius.setter
    def celsius(self, value):
        if value < -273.15:
            raise ValueError("too cold")
        self._celsius = value
```

SimPy 的 `Event.defused` 就使用了 setter，不过它的 setter 只允许把失败事件标记为已消解。

### SimPy 场景

`Environment.now`：

```python
@property
def now(self):
    return self._now
```

`Event.triggered`：

```python
@property
def triggered(self):
    return self._value is not PENDING
```

`Resource.count`：

```python
@property
def count(self):
    return len(self.users)
```

### 最小实战

```python
class Resource:
    def __init__(self):
        self.users = []

    @property
    def count(self):
        return len(self.users)


resource = Resource()
resource.users.append("A")
print(resource.count)
```

如果你把 `count` 写成普通方法：

```python
resource.count()
```

也能实现类似功能。但 SimPy 选择 `resource.count`，是因为它更像“状态”，不是“动作”。

### 阅读提示

看到 `obj.xxx` 不一定是普通字段，可能是 `@property` 方法。读源码时搜索：

```text
@property
def xxx
```

属性方法可能看起来很轻，但里面也可以写复杂逻辑。读源码时不要只看调用处，要跳到属性定义处确认它是否只是简单返回字段。

## 6. 单下划线私有约定

### 定义与概念

Python 没有强制私有字段。单下划线 `_name` 是约定：这是内部实现，外部不应直接依赖。

约定含义：

- `name`：公开字段或方法，外部可以使用。
- `_name`：内部实现细节，外部尽量不要依赖。
- `__name`：名称改写，避免子类意外覆盖，较少用于 SimPy 主线。

### 语法

```python
self._value = value
```

公开属性通常会包一层：

```python
@property
def value(self):
    return self._value
```

这样外部读 `event.value`，内部仍可控制 `_value` 的访问规则。

### SimPy 场景

事件内部状态：

```python
self._ok
self._value
self._defused
```

环境内部状态：

```python
self._queue
self._now
self._active_proc
```

### 最小实战

```python
class Counter:
    def __init__(self):
        self._count = 0

    @property
    def count(self):
        return self._count
```

### 阅读提示

读源码可以看 `_value`、`_queue`，但业务代码最好使用公开 API，例如 `event.value`、`env.now`。

例如 `event._value` 在事件未触发时可能是 `PENDING` 哨兵对象，而 `event.value` 会在未触发时抛出更清晰的错误。公开 API 通常包含更好的保护。

## 7. 自定义异常

### 定义与概念

异常用于表示错误或特殊控制流。自定义异常可以携带领域含义。

异常传播规则：

1. `raise` 抛出异常。
2. Python 沿调用栈向外找匹配的 `except`。
3. 找到后执行对应处理代码。
4. 找不到就终止程序并打印 traceback。

SimPy 的中断也利用这套机制，只不过异常不是用户代码直接 `raise`，而是调度器用 `generator.throw()` 注入进程。

### 语法

```python
class MyError(Exception):
    pass

raise MyError("broken")
```

异常对象的参数会保存在 `args` 中：

```python
err = ValueError("bad value")
print(err.args)
```

### SimPy 场景

SimPy 定义：

```python
class SimPyException(Exception):
    pass


class Interrupt(SimPyException):
    ...
```

`Interrupt` 表示进程被中断，不只是普通错误，也是仿真调度机制的一部分。

### 最小实战

```python
class Interrupt(Exception):
    def __init__(self, cause):
        super().__init__(cause)

    @property
    def cause(self):
        return self.args[0]


try:
    raise Interrupt("preempted")
except Interrupt as exc:
    print(exc.cause)
```

这个例子里：

```python
super().__init__(cause)
```

会把 `cause` 放进标准异常字段 `args`。所以 `cause` 属性可以通过 `self.args[0]` 读出来。

### 阅读提示

读异常类时看：

- 继承谁。
- `args` 里保存什么。
- 是否提供 `@property`。
- 是否重写 `__str__()`。

SimPy 的 `Interrupt` 本身不是“错误失败”的意思。它更像一种控制信号：外部告诉进程“你现在等待的事情被打断了，请在 `except simpy.Interrupt` 中决定怎么处理”。

## 8. try / except / finally

### 定义与概念

`try/except` 捕获异常，`finally` 无论是否异常都会执行。SimPy 进程常用它处理中断和清理。

基本执行规则：

- `try` 中没有异常：跳过 `except`，执行 `finally`。
- `try` 中有异常且被捕获：执行对应 `except`，再执行 `finally`。
- `try` 中有异常但没被捕获：先执行 `finally`，再继续向外抛异常。

### 语法

```python
try:
    risky()
except SomeError:
    handle()
finally:
    cleanup()
```

多个异常可以分开捕获：

```python
try:
    run()
except ValueError:
    print("bad value")
except RuntimeError:
    print("runtime error")
```

### SimPy 场景

用户进程：

```python
try:
    yield env.timeout(10)
except simpy.Interrupt as interrupt:
    print(interrupt.cause)
```

SimPy 内部 `Process._resume()` 捕获生成器结束：

```python
try:
    next(generator)
except StopIteration as e:
    pass
```

### 最小实战

```python
class Interrupt(Exception):
    pass


try:
    raise Interrupt("stop")
except Interrupt as exc:
    print("caught", exc)
finally:
    print("cleanup")
```

结合生成器看中断：

```python
class Interrupt(Exception):
    pass


def worker():
    try:
        yield "waiting"
    except Interrupt:
        print("handle interrupt")
    finally:
        print("always cleanup")


g = worker()
next(g)
try:
    g.throw(Interrupt())
except StopIteration:
    pass
```

这和 SimPy 进程在 `yield env.timeout(...)` 处被中断的行为非常接近。

### 阅读提示

在 `Process._resume()` 中，`StopIteration` 不是错误，而是进程正常结束。

读 `try/except` 时一定要看捕获范围。SimPy 的 `Process._resume()` 捕获 `BaseException`，是为了把用户进程内部抛出的任何异常转换成失败的 `Process` 事件。

## 9. 生成器函数和 yield

### 定义与概念

函数体中出现 `yield`，这个函数就是生成器函数。调用它不会立即执行函数体，而是返回生成器对象。

普通函数和生成器函数最大的区别：

```python
def normal():
    print("run")
    return 1


def generator():
    print("run")
    yield 1
```

调用 `normal()` 会立刻执行函数体；调用 `generator()` 不会立刻执行函数体，只会返回一个生成器对象。只有调用 `next(g)` 或 `g.send(...)` 时，生成器才真正开始运行。

生成器可以暂停。执行到 `yield` 时，它会：

1. 把 `yield` 后面的值交给外部。
2. 保存当前局部变量和执行位置。
3. 暂停执行。
4. 下次恢复时，从同一个 `yield` 后面继续。

### 语法

```python
def gen():
    yield 1
    yield 2


g = gen()
print(next(g))
print(next(g))
```

生成器执行第三次 `next(g)` 时没有更多 `yield`，会抛出 `StopIteration`：

```python
try:
    print(next(g))
except StopIteration:
    print("generator exhausted")
```

### SimPy 场景

SimPy 进程就是生成器：

```python
def car(env):
    yield env.timeout(5)
```

`yield event` 表示当前进程暂停，等待事件完成。

### 最小实战

```python
def process():
    print("start")
    yield "wait-event"
    print("resume")


g = process()
event = next(g)
print("yielded:", event)
try:
    next(g)
except StopIteration:
    print("finished")
```

逐步理解这个例子：

1. `g = process()`：只创建生成器，不打印 `start`。
2. `next(g)`：开始执行，打印 `start`，遇到 `yield "wait-event"` 暂停。
3. 外部拿到 `"wait-event"`。
4. 再次 `next(g)`：从暂停处继续，打印 `resume`。
5. 函数结束，抛出 `StopIteration`。

### 阅读提示

看到 `yield` 时，要同时理解两层含义：

- 用户视角：等待事件。
- 源码视角：生成器暂停，把事件对象交给调度器。

SimPy 里的 `yield env.timeout(5)` 不会让 Python 线程睡眠 5 秒。它只是让进程生成器暂停，并把 `Timeout` 事件交给 `Environment`。环境以后处理这个事件时，再恢复该生成器。

## 10. yield 表达式、send() 和事件值

### 定义与概念

`yield` 是表达式。生成器恢复时，外部可以用 `send(value)` 把值送回 `yield` 位置。

很多初学者以为 `yield` 只能“吐出”值。实际上它有两个方向：

```text
生成器 -> 外部：yield 后面的对象
外部 -> 生成器：send(value) 送回的对象
```

所以这行：

```python
def process():
    result = yield event
```

可以拆成两步理解：

1. 先把 `event` 交给外部，生成器暂停。
2. 外部未来用 `send(value)` 恢复生成器，`value` 变成 `result`。

### 语法

```python
def gen():
    value = yield "need-value"
    print("got", value)


g = gen()
print(next(g))
g.send("hello")
```

注意：生成器刚创建后，第一次启动通常用 `next(g)` 或 `g.send(None)`，不能直接 `g.send("hello")`。因为生成器还没运行到第一个 `yield`，没有地方接收这个值。

### SimPy 场景

用户写：

```python
def process():
    value = yield event
```

事件成功后，`value` 是事件的 `_value`。内部在 `Process._resume()` 中：

```python
event = self._generator.send(event._value)
```

这行代码同时做了两件事：

1. 把上一个事件的结果送回用户生成器。
2. 接收用户生成器下一次 `yield` 出来的事件。

如果用户进程写：

```python
result = yield env.timeout(5, value="ok")
next_event = env.timeout(1)
yield next_event
```

那么第一次恢复时，`send("ok")` 会让 `result` 得到 `"ok"`，然后进程继续运行到 `yield next_event`，把新的等待事件交回 SimPy。

### 最小实战

```python
def waiter():
    result = yield "event"
    print("event result:", result)


g = waiter()
yielded = next(g)
print("waiting on", yielded)
try:
    g.send("done")
except StopIteration:
    pass
```

可以用更直观的日志看执行顺序：

```python
def dialogue():
    print("A: before yield")
    answer = yield "question"
    print("A: got", answer)


g = dialogue()
question = next(g)
print("outside got:", question)
try:
    g.send("answer")
except StopIteration:
    print("dialogue finished")
```

### 阅读提示

把两端对上：

```text
用户进程：value = yield event
源码恢复：generator.send(event._value)
```

读 `Process._resume()` 时，变量名 `event` 会变化：一开始它是“刚完成的事件”，调用 `send()` 后，它变成“用户进程新 yield 出来的事件”。这是源码初读时最容易混乱的点。

## 11. 生成器 return 和 StopIteration

### 定义与概念

生成器中的 `return value` 会结束生成器，并把 `value` 放进 `StopIteration.value`。

普通函数的 `return value` 是直接把值返回给调用方。生成器不同：它可能已经暂停过多次，所以最终返回值要通过结束时的 `StopIteration` 携带出来。

### 语法

```python
def gen():
    yield 1
    return "done"


g = gen()
next(g)
try:
    next(g)
except StopIteration as exc:
    print(exc.value)
```

在 Python 3 中，`StopIteration.value` 等价于它的第一个参数。SimPy 源码中使用：

```python
e.args[0] if len(e.args) else None
```

这是为了兼容没有返回值的生成器。

### SimPy 场景

进程可以返回结果：

```python
def task(env):
    yield env.timeout(1)
    return "ok"
```

`Process._resume()` 捕获后让 `Process` 事件成功：

```python
self._ok = True
self._value = e.args[0] if len(e.args) else None
```

### 最小实战

```python
def task():
    yield "wait"
    return 42


g = task()
next(g)
try:
    next(g)
except StopIteration as exc:
    print("return value:", exc.value)
```

没有显式 `return` 时：

```python
def task():
    yield "wait"


g = task()
next(g)
try:
    next(g)
except StopIteration as exc:
    print(exc.value)
```

输出是 `None`。这就是 SimPy 进程没有返回值时，`Process.value` 为 `None` 的来源。

### 阅读提示

`yield env.process(task(env))` 能拿到子进程返回值，根源就是生成器 `return` 变成了 `Process._value`。

如果用户进程内部抛出普通异常，不会走 `StopIteration` 分支，而会走 `except BaseException` 分支，进程事件会失败。

## 12. generator.throw() 和中断

### 定义与概念

`generator.throw(exc)` 会在生成器当前暂停的 `yield` 位置抛出异常。

它可以理解成：外部不再用正常值恢复生成器，而是在暂停点“塞进去一个异常”。如果生成器内部有匹配的 `try/except`，就可以捕获这个异常并继续处理。

### 语法

```python
g.throw(RuntimeError("broken"))
```

如果生成器不捕获这个异常，异常会从 `throw()` 调用处继续抛出来。

### SimPy 场景

进程中断依靠 `throw()`：

```python
event = self._generator.throw(exc)
```

用户进程在 `yield` 处收到异常：

```python
try:
    yield env.timeout(10)
except simpy.Interrupt:
    ...
```

### 最小实战

```python
class Interrupt(Exception):
    pass


def worker():
    try:
        yield "sleep"
    except Interrupt as exc:
        print("interrupted:", exc)


g = worker()
print(next(g))
try:
    g.throw(Interrupt("stop"))
except StopIteration:
    pass
```

如果不捕获中断：

```python
class Interrupt(Exception):
    pass


def worker():
    yield "sleep"


g = worker()
next(g)
try:
    g.throw(Interrupt("stop"))
except Interrupt as exc:
    print("outside caught:", exc)
```

这对应 SimPy 中“进程没有处理异常，于是 Process 事件失败”的情况。

### 阅读提示

`Process.interrupt()` 不会立即打断 Python 正在执行的代码。它创建 `Interruption` 事件，等环境处理该事件时再 `throw()`。

读中断链路时按这个顺序：

1. `process.interrupt(cause)` 创建 `Interruption` 事件。
2. `Interruption` 被放进环境队列，优先级是 `URGENT`。
3. 环境 `step()` 处理它。
4. `Interruption._interrupt()` 移除进程在原目标事件上的恢复回调。
5. 调用 `process._resume(self)`。
6. `_resume()` 看到事件失败，用 `generator.throw(Interrupt(cause))` 恢复用户进程。

## 13. 上下文管理器 with

### 定义与概念

上下文管理器用于进入和退出一个受控范围。进入时调用 `__enter__()`，退出时调用 `__exit__()`。

它最常见的用途是“保证清理”。例如打开文件后一定要关闭，获得资源后一定要释放，请求排队后如果中途退出一定要取消。

### 语法

```python
with obj as value:
    ...
```

近似等价于：

```python
value = obj.__enter__()
try:
    ...
finally:
    obj.__exit__(...)
```

真实展开更接近：

```python
manager = obj
value = manager.__enter__()
try:
    ...
except BaseException as exc:
    suppress = manager.__exit__(type(exc), exc, exc.__traceback__)
    if not suppress:
        raise
else:
    manager.__exit__(None, None, None)
```

所以 `__exit__()` 能知道是否因为异常退出。

### SimPy 场景

资源请求支持：

```python
with resource.request() as req:
    yield req
    yield env.timeout(5)
```

`Request.__exit__()` 会释放资源。`Put.__exit__()` 和 `Get.__exit__()` 会取消尚未触发的请求。

这个设计很重要：如果进程在等待资源时被中断，`with` 会触发 `__exit__()`，把尚未成功的请求从队列里移除，避免队列中留下“没人等的请求”。

### 最小实战

```python
class Request:
    def __enter__(self):
        print("enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        print("exit", exc_type)


with Request() as req:
    print("inside")
```

异常情况下也会执行 `__exit__()`：

```python
class Manager:
    def __enter__(self):
        print("enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        print("exit", exc_type.__name__ if exc_type else None)


try:
    with Manager():
        raise RuntimeError("boom")
except RuntimeError:
    print("outside caught")
```

### 阅读提示

重点看 `__exit__()`：

- 返回 `True` 会吞掉异常。
- 返回 `None` 或 `False` 不吞异常。
- SimPy 中通常用它做资源释放和队列清理。

`with resource.request() as req:` 里的 `req` 不是资源本身，而是请求事件。请求成功后，它代表“当前进程占用了一个资源槽”。退出 `with` 时，SimPy 用这个请求事件找到并释放对应槽位。

## 14. 回调函数和回调列表

### 定义与概念

回调是“稍后由别人调用的函数”。SimPy 的事件完成时会执行回调列表。

初级读者可以把回调理解为“登记手机号，事情办完后通知我”。事件没有立即恢复进程，而是先记录：

```text
这个事件完成时，请调用 process._resume(event)
```

事件完成以后，环境统一处理这些登记过的函数。

### 语法

```python
callbacks = []
callbacks.append(func)
for callback in callbacks:
    callback(event)
```

函数对象可以保存到变量：

```python
def hello(name):
    print("hello", name)


f = hello
f("SimPy")
```

方法也可以保存到列表：

```python
callbacks = [obj.method]
```

之后调用 `callbacks[0](event)` 时，`obj` 已经绑定在方法里。

### SimPy 场景

事件有回调列表：

```python
self.callbacks = []
```

进程等待事件时：

```python
event.callbacks.append(self._resume)
```

环境处理事件时：

```python
for callback in callbacks:
    callback(event)
```

为什么不是事件一成功就立刻执行回调？因为 SimPy 要保证所有状态变化都经过环境事件队列。`event.succeed()` 只是把事件标记为成功并调度进队列，真正执行回调发生在后续的 `env.step()`。

### 最小实战

```python
class Event:
    def __init__(self):
        self.callbacks = []
        self.value = None

    def succeed(self, value):
        self.value = value
        for callback in self.callbacks:
            callback(self)


def on_done(event):
    print("done:", event.value)


event = Event()
event.callbacks.append(on_done)
event.succeed("ok")
```

更接近 SimPy 的版本：

```python
class Environment:
    def __init__(self):
        self.queue = []

    def schedule(self, event):
        self.queue.append(event)

    def step(self):
        event = self.queue.pop(0)
        callbacks, event.callbacks = event.callbacks, None
        for callback in callbacks:
            callback(event)


class Event:
    def __init__(self, env):
        self.env = env
        self.callbacks = []
        self.value = None

    def succeed(self, value):
        self.value = value
        self.env.schedule(self)


env = Environment()
event = Event(env)
event.callbacks.append(lambda event: print(event.value))
event.succeed("ok")
env.step()
```

这里 `succeed()` 不直接打印，`env.step()` 才打印。

### 阅读提示

SimPy 中 `callbacks is None` 表示事件已经处理完毕，不等于“没有回调”。

如果事件还没处理，但没有等待者，`callbacks` 是空列表 `[]`。如果事件已经处理完，`callbacks` 是 `None`。这两个状态在 SimPy 中语义完全不同。

## 15. 函数是一等对象、lambda 和闭包

### 定义与概念

函数可以像普通对象一样传递、保存和调用。`lambda` 是匿名函数。闭包是内部函数引用外部函数变量。

“函数是一等对象”的意思是：

- 可以把函数赋值给变量。
- 可以把函数放进列表或字典。
- 可以把函数作为参数传给另一个函数。
- 可以从函数中返回另一个函数。

SimPy 回调、过滤器、条件判断都依赖这个能力。

### 语法

```python
def rule(x):
    return x > 0

func = rule
print(func(3))

key = lambda item: item["priority"]
```

`lambda item: item["priority"]` 等价于：

```python
def key(item):
    return item["priority"]
```

只是 `lambda` 更适合写短函数。

### SimPy 场景

`Condition` 接收判断函数：

```python
self._evaluate = evaluate
```

`FilterStore` 接收过滤函数：

```python
store.get(lambda item: item["type"] == "gpu")
```

`util.start_delayed()` 定义内部生成器 `starter()`，它引用外部的 `env`、`generator`、`delay`，这就是闭包。

### 最小实战

```python
def make_filter(target_type):
    def filter_item(item):
        return item["type"] == target_type
    return filter_item


items = [{"type": "cpu"}, {"type": "gpu"}]
filter_gpu = make_filter("gpu")
print([item for item in items if filter_gpu(item)])
```

闭包中，内部函数会记住外部变量：

```python
def make_adder(base):
    def add(x):
        return base + x
    return add


add10 = make_adder(10)
print(add10(5))
```

`start_delayed()` 中的内部生成器 `starter()` 也是类似机制：它记住了外部传入的 `env`、`generator`、`delay`。

### 阅读提示

看到参数名叫 `callback`、`evaluate`、`filter`、`key`，它通常是函数对象。

读 `lambda e: e.key` 时，可以在脑子里翻译成“给我一个 e，返回 e.key”。

## 16. heapq、元组排序键和 itertools.count()

### 定义与概念

`heapq` 是最小堆，可以快速取出最小元素。元组比较按从左到右逐项比较。`itertools.count()` 创建无限递增计数器。

普通列表如果每次都排序，成本较高。堆适合这种场景：

- 不断插入新事件。
- 每次只需要拿出“最早发生”的事件。

`heapq` 保证 `heap[0]` 总是当前最小元素，但整个列表不一定完全有序。

### 语法

```python
from heapq import heappush, heappop
from itertools import count

eid = count()
queue = []
heappush(queue, (time, priority, next(eid), event))
```

元组比较示例：

```python
print((5, 1) < (10, 0))
print((10, 0) < (10, 1))
print((10, 1, 2) < (10, 1, 3))
```

第一项不同先比第一项；第一项相同再比第二项；以此类推。

### SimPy 场景

`Environment.schedule()`：

```python
heappush(self._queue, (self._now + delay, priority, next(self._eid), event))
```

排序含义：

```text
time -> priority -> eid
```

所以仿真时间更早的事件先处理；同一时间下 `URGENT=0` 先于 `NORMAL=1`；再相同就按事件编号 FIFO。

### 最小实战

```python
from heapq import heappush, heappop
from itertools import count

eid = count()
queue = []

heappush(queue, (10, 1, next(eid), "normal"))
heappush(queue, (10, 0, next(eid), "urgent"))
heappush(queue, (5, 1, next(eid), "early"))

while queue:
    print(heappop(queue))
```

输出顺序会是：

```text
(5, 1, ..., "early")
(10, 0, ..., "urgent")
(10, 1, ..., "normal")
```

这说明时间最早优先；同时间下优先级数字小的优先。

### 阅读提示

读 `core.py` 时，先把事件队列理解成按 `(time, priority, eid)` 排序的堆。

`eid` 的作用是避免两个事件时间和优先级都相同时直接比较 `event` 对象。很多事件对象本身不可比较，如果元组前几项相同而没有 `eid`，堆可能会尝试比较事件对象并报错。

## 17. object() 哨兵、is 和 ==

### 定义与概念

`object()` 可以创建唯一哨兵对象。`is` 比较是不是同一个对象，`==` 比较值是否相等。

为什么不用 `None` 表示未完成？因为事件成功后的值也可能合法地是 `None`。例如：

```python
event.succeed(None)
```

如果用 `None` 表示未完成，就无法区分“还没完成”和“完成了但值是 None”。

### 语法

```python
PENDING = object()

if value is PENDING:
    print("not ready")
```

`is` 检查对象身份：

```python
a = []
b = []
c = a
print(a == b)
print(a is b)
print(a is c)
```

两个空列表值相等，但不是同一个对象。

### SimPy 场景

`events.py` 中：

```python
PENDING = object()
```

事件未触发：

```python
self._value is PENDING
```

事件成功且返回值就是 `None`：

```python
self._value is None
```

两者不能混淆。

### 最小实战

```python
PENDING = object()


class Future:
    def __init__(self):
        self.value = PENDING

    @property
    def ready(self):
        return self.value is not PENDING


f = Future()
print(f.ready)
f.value = None
print(f.ready)
```

### 阅读提示

状态哨兵一般用 `is`。业务值比较一般用 `==`。

读到 `if event._value is not PENDING:` 时，不要理解成普通数值比较。它是在判断事件是否已经被触发。

## 18. 魔术方法：repr、str、lt

### 定义与概念

双下划线方法会被 Python 语法自动调用。

这些方法不是你主动调用的普通方法，而是 Python 在特定语法下替你调用。例如：

```python
print(obj)
```

内部会尝试调用：

```python
obj.__str__()
```

排序时：

```python
a < b
```

内部会调用：

```python
a.__lt__(b)
```

| 方法 | 触发场景 |
| --- | --- |
| `__repr__` | `repr(obj)`、调试输出 |
| `__str__` | `str(obj)`、`print(obj)` |
| `__lt__` | `<`、排序、堆 |

### 语法

```python
class Item:
    def __lt__(self, other):
        return self.priority < other.priority
```

### SimPy 场景

`PriorityItem.__lt__()` 让 `PriorityStore` 可以用堆排序：

```python
def __lt__(self, other):
    return self.priority < other.priority
```

`Interrupt.__str__()` 让日志显示更清楚。

`Event.__repr__()` 让调试时能看到更有意义的事件描述，而不是默认对象信息。

### 最小实战

```python
from heapq import heappush, heappop


class PriorityItem:
    def __init__(self, priority, item):
        self.priority = priority
        self.item = item

    def __lt__(self, other):
        return self.priority < other.priority

    def __repr__(self):
        return f"PriorityItem({self.priority}, {self.item!r})"


heap = []
heappush(heap, PriorityItem(5, "low"))
heappush(heap, PriorityItem(1, "high"))
print(heappop(heap))
```

如果去掉 `__lt__()`，两个 `PriorityItem` 对象就不知道怎么比较大小，放进堆后在某些情况下会报错。

### 阅读提示

一个对象如果直接放入 `heapq`，必须可比较，或者外层元组必须可比较。

读魔术方法时，要反向对应到语法：

- 看到 `__lt__`，去找哪里用了排序、`heapq`、`min`、`max`。
- 看到 `__contains__`，去找哪里用了 `in`。
- 看到 `__getitem__`，去找哪里用了 `obj[key]`。
- 看到 `__enter__` / `__exit__`，去找哪里用了 `with`。

## 19. NamedTuple

### 定义与概念

`NamedTuple` 是带字段名的不可变元组。它比普通类轻量，又能通过属性名访问字段。

普通元组只能用下标访问：

```python
item = (1, "urgent")
print(item[0])
print(item[1])
```

`NamedTuple` 可以用名字访问：

```python
print(item.priority)
print(item.item)
```

这让代码更容易读。

### 语法

```python
from typing import NamedTuple


class Point(NamedTuple):
    x: int
    y: int
```

### SimPy 场景

`PriorityItem`：

```python
class PriorityItem(NamedTuple):
    priority: Any
    item: Any
```

它把优先级和业务对象绑定在一起。

### 最小实战

```python
from typing import NamedTuple


class PriorityItem(NamedTuple):
    priority: int
    item: str


p = PriorityItem(1, "urgent")
print(p.priority, p.item)
```

它仍然像元组：

```python
priority, item = p
print(priority, item)
```

### 阅读提示

`NamedTuple` 对象通常不可变。需要修改时创建新对象。

在 `PriorityStore` 中，`PriorityItem` 的核心意义是“排序用 priority，业务对象放 item”。读源码时不要把 `priority` 和 `item` 的职责混在一起。

## 20. 运算符重载：__and__ 和 __or__

### 定义与概念

类可以定义运算符行为。`a & b` 调用 `a.__and__(b)`；`a | b` 调用 `a.__or__(b)`。

这就是为什么同一个符号在不同对象上含义不同：

- 整数上：`1 | 2` 是按位或。
- 集合上：`{1} | {2}` 是集合并集。
- SimPy 事件上：`event1 | event2` 是等待任意一个事件完成。

### 语法

```python
class X:
    def __or__(self, other):
        return ("or", self, other)
```

### SimPy 场景

事件组合：

```python
event_a & event_b
event_a | event_b
```

底层是：

```python
def __and__(self, other):
    return Condition(self.env, Condition.all_events, [self, other])

def __or__(self, other):
    return Condition(self.env, Condition.any_events, [self, other])
```

### 最小实战

```python
class Event:
    def __init__(self, name):
        self.name = name

    def __or__(self, other):
        return f"AnyOf({self.name}, {other.name})"

    def __and__(self, other):
        return f"AllOf({self.name}, {other.name})"


a = Event("a")
b = Event("b")
print(a | b)
print(a & b)
```

调用顺序可以手动写出来：

```python
print(a.__or__(b))
print(a.__and__(b))
```

结果等价，只是直接写 `a | b` 更像“事件组合表达式”。

### 阅读提示

`yield req | timeout` 不是位运算，而是构造 `AnyOf` 条件事件。

注意运算符优先级。实际写复杂条件时，建议加括号：

```python
def process():
    result = yield (event_a | event_b)
```

这样初学者读起来更清楚。

## 21. __getitem__、__contains__、__iter__

### 定义与概念

这些魔术方法让对象表现得像容器：

| 语法 | 调用方法 |
| --- | --- |
| `obj[key]` | `obj.__getitem__(key)` |
| `key in obj` | `obj.__contains__(key)` |
| `for x in obj` | `obj.__iter__()` |

这就是 Python “协议”的思想：一个对象不一定真的继承 `dict` 或 `list`，只要实现对应方法，就能支持类似语法。

### SimPy 场景

`ConditionValue` 支持：

```python
if req in result:
    value = result[req]
```

还支持：

```python
result.keys()
result.values()
result.items()
```

### 最小实战

```python
class Result:
    def __init__(self):
        self.data = {"event-a": "ok"}

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __iter__(self):
        return iter(self.data)


r = Result()
print("event-a" in r)
print(r["event-a"])
print(list(r))
```

如果希望它更像字典，还可以加 `items()`：

```python
class Result:
    def __init__(self):
        self.data = {"event-a": "ok"}

    def items(self):
        return self.data.items()


r = Result()
print(list(r.items()))
```

### 阅读提示

条件事件结果看起来像字典，但它是自定义对象。

所以不要看到 `result[req]` 就直接去找 `dict`。应先找 `result` 的类型，这里是 `ConditionValue`，然后看它的 `__getitem__()`。

## 22. 描述符 __get__ 和 BoundClass

### 定义与概念

描述符是定义了 `__get__()`、`__set__()` 或 `__delete__()` 的对象。它可以控制属性访问行为。

这是本文最抽象的语法点。可以先从普通属性查找开始：

```python
obj.x
```

Python 大致会查：

1. 对象自己的属性字典 `obj.__dict__`。
2. 类的属性字典 `type(obj).__dict__`。
3. 父类的属性字典。

如果类属性不是普通值，而是实现了 `__get__()` 的对象，那么访问它时，Python 会调用这个 `__get__()`。这就是描述符。

### 语法

```python
class Descriptor:
    def __get__(self, instance, owner):
        return "computed value"


class A:
    x = Descriptor()


print(A().x)
```

这个例子里，`A().x` 没有直接返回 `Descriptor` 对象，而是返回 `__get__()` 的结果 `"computed value"`。

### SimPy 场景

`BoundClass` 是 SimPy 源码里最关键的高级语法之一。它让类构造器看起来像实例方法：

```python
env.timeout(5)
```

本质上等价于：

```python
Timeout(env, 5)
```

核心逻辑：

```python
def __get__(self, instance, owner=None):
    if instance is None:
        return self.cls
    return MethodType(self.cls, instance)
```

这段代码要分两种情况：

```python
Environment.timeout
```

在类上访问，`instance is None`，返回原始 `Timeout` 类。

```python
env.timeout
```

在实例上访问，`instance` 是 `env`，返回绑定了 `env` 的方法。

### 最小实战

```python
from types import MethodType


class BoundClass:
    def __init__(self, cls):
        self.cls = cls

    def __get__(self, instance, owner=None):
        if instance is None:
            return self.cls
        return MethodType(self.cls, instance)


class Event:
    def __init__(self, env, value):
        self.env = env
        self.value = value


class Env:
    event = BoundClass(Event)


env = Env()
event = env.event("ok")
print(event.env is env, event.value)
```

执行过程：

1. Python 看到 `env.event`。
2. `event` 是 `Env` 类上的 `BoundClass(Event)`。
3. Python 调用 `BoundClass.__get__(bound_class, env, Env)`。
4. 返回 `MethodType(Event, env)`。
5. 调用 `env.event("ok")` 时，相当于调用 `Event(env, "ok")`。

### 阅读提示

如果找不到 `Environment.timeout()` 的普通方法定义，不要困惑。运行时它来自：

```python
timeout = BoundClass(Timeout)
```

读 `BoundClass` 时一定要记住：它的作用是减少样板代码。用户写 `env.timeout(5)`，不用每次手动写 `Timeout(env, 5)`。

## 23. MethodType 和提前绑定

### 定义与概念

`MethodType(func_or_class, instance)` 可以创建绑定方法。调用绑定方法时，`instance` 会自动作为第一个参数传入。

普通函数和绑定方法的区别：

```python
def f(self, x):
    ...
```

如果直接调用：

```python
f(obj, 1)
```

需要手动传 `obj`。如果它变成绑定方法：

```python
obj.f(1)
```

`obj` 会自动传进去。

### 语法

```python
from types import MethodType

bound = MethodType(func, obj)
```

### SimPy 场景

`BoundClass.bind_early(instance)` 会把类里的 `BoundClass` 描述符提前解析成绑定方法，再写回实例字典：

```python
bound_class = getattr(instance, name)
setattr(instance, name, bound_class)
```

这是性能优化，减少仿真循环中的描述符解析开销。

### 最小实战

```python
from types import MethodType


def hello(self, name):
    return f"{self.prefix} {name}"


class Greeter:
    prefix = "hi"


g = Greeter()
g.hello = MethodType(hello, g)
print(g.hello("SimPy"))
```

这里调用：

```python
g.hello("SimPy")
```

实际等价于：

```python
hello(g, "SimPy")
```

### 阅读提示

`bind_early()` 不改变语义，只是把动态解析结果缓存到实例上。

为什么要提前绑定？因为仿真模型可能创建大量事件，`env.timeout()` 会被频繁调用。每次都走描述符解析会有一点额外成本，所以 SimPy 在环境初始化时先把这些方法绑定好。

## 24. TYPE_CHECKING 和运行时分支

### 定义与概念

`typing.TYPE_CHECKING` 在类型检查器中为 `True`，程序运行时为 `False`。它常用于给 IDE 提供类型信息，同时让运行时走动态实现。

初级读者要特别注意：`TYPE_CHECKING` 分支里的代码通常不是运行时执行路径。它主要给编辑器、补全、类型检查工具看。

### 语法

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    ...
else:
    ...
```

### SimPy 场景

`Environment` 中：

```python
if TYPE_CHECKING:
    def timeout(self, delay, value=None) -> Timeout:
        return Timeout(self, delay, value)
else:
    timeout = BoundClass(Timeout)
```

运行时走 `BoundClass`；类型检查时 IDE 看到普通方法签名。

### 最小实战

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    def func(x: int) -> int:
        ...
else:
    def func(x):
        return x


print(func("runtime accepts this"))
```

这个例子运行时会走 `else` 分支，所以即使 `TYPE_CHECKING` 分支写了 `x: int`，运行时仍然可以传字符串。

### 阅读提示

读运行逻辑看 `else`；读接口签名看 `TYPE_CHECKING` 分支。

SimPy 为什么这么写？因为运行时 `timeout = BoundClass(Timeout)` 很动态，IDE 很难知道 `env.timeout(delay, value)` 的参数是什么。`TYPE_CHECKING` 分支手写一个“假的普通方法签名”，让 IDE 能补全和检查。

## 25. 类型标注、泛型和 NewType

### 定义与概念

类型标注表达接口意图，默认不会在运行时强制检查。

例如：

```python
def add(x: int, y: int) -> int:
    return x + y
```

这不代表 Python 运行时一定拒绝字符串：

```python
print(add("a", "b"))
```

它仍可能输出 `"ab"`。类型标注主要帮助人和工具理解代码。

常见类型：

| 类型 | 含义 |
| --- | --- |
| `Any` | 任意类型 |
| `Optional[T]` | `T` 或 `None` |
| `Union[A, B]` | A 或 B |
| `Callable[[A], B]` | 接收 A 返回 B 的函数 |
| `TypeVar` | 类型变量 |
| `Generic[T]` | 泛型类 |
| `NewType` | 静态类型层面的新语义类型 |

### 语法

```python
from typing import Any, Callable, Generic, NewType, Optional, TypeVar, Union

T = TypeVar("T")

class Box(Generic[T]):
    def __init__(self, value: T):
        self.value = value

Priority = NewType("Priority", int)
```

逐个解释：

- `Any`：我不限制类型。
- `Optional[int]`：可以是 `int`，也可以是 `None`。
- `Union[int, float]`：可以是 `int` 或 `float`。
- `Callable[[int], str]`：一个函数，接收 `int`，返回 `str`。
- `TypeVar("T")`：定义一个类型变量。
- `Generic[T]`：这个类带一个类型参数。
- `NewType("Priority", int)`：给 `int` 起一个更有语义的新类型名。

### SimPy 场景

仿真时间：

```python
SimTime = Union[int, float]
```

事件优先级：

```python
EventPriority = NewType('EventPriority', int)
URGENT = EventPriority(0)
NORMAL = EventPriority(1)
```

事件回调：

```python
EventCallback = Callable[[EventType], None]
```

资源泛型：

```python
ResourceType = TypeVar('ResourceType', bound='BaseResource')
```

### 最小实战

```python
from typing import Callable, Generic, NewType, Optional, TypeVar

T = TypeVar("T")
Priority = NewType("Priority", int)


class Box(Generic[T]):
    def __init__(self, value: T):
        self.value = value


def apply(callback: Callable[[int], str], value: Optional[int]) -> str:
    if value is None:
        return "none"
    return callback(value)


print(Box[int](3).value)
print(Priority(0) < Priority(1))
print(apply(lambda x: str(x * 2), 3))
```

泛型最常见的直觉是“盒子里装什么，拿出来还是什么”：

```python
box = Box[int](3)
value: int = box.value
```

`Box[str]` 则表示盒子里装字符串。

### 阅读提示

类型标注主要帮助你理解“作者希望这个对象是什么”。真正运行行为仍要看方法体。

读 SimPy 的类型标注时，不必一开始完全掌握所有泛型细节。可以先抓住关键名词：

- `Event`：事件。
- `Process`：进程事件。
- `Environment`：环境。
- `Put` / `Get`：资源操作事件。
- `Callable`：函数。
- `Optional`：可能是 `None`。

## 26. from __future__ import annotations

### 定义与概念

这行语句会延迟解析类型标注，允许在类定义内部引用尚未完全定义的类型。

没有这行时，如果类型名还没定义，标注可能会报错。开启后，Python 会把很多标注先当作字符串保存，之后再由类型工具解析。

### 语法

```python
from __future__ import annotations

class Node:
    def connect(self, other: Node) -> None:
        ...
```

### SimPy 场景

SimPy 多个文件开头都有：

```python
from __future__ import annotations
```

它主要服务类型标注，不改变事件调度逻辑。

### 最小实战

```python
from __future__ import annotations


class Node:
    def __init__(self, name: str):
        self.name = name

    def connect(self, other: Node) -> tuple[Node, Node]:
        return self, other
```

### 阅读提示

读运行主线时可以先忽略它；读类型标注时知道它允许前向引用即可。

它不改变 `yield`、事件队列、资源请求这些运行机制。

## 27. 列表修改和队列不变量

### 定义与概念

在遍历列表时删除元素，需要小心维护下标。SimPy 资源队列会在循环中删除已触发请求。

错误写法：

```python
items = [1, 2, 3, 4]
for item in items:
    if item % 2 == 0:
        items.remove(item)
```

遍历时修改列表可能跳过元素。SimPy 使用 `while idx < len(queue)` 手动控制下标，就是为了避免这个问题。

### 语法

```python
item = queue[idx]
removed = queue.pop(idx)
```

### SimPy 场景

`BaseResource._trigger_put()`：

```python
idx = 0
while idx < len(self.put_queue):
    put_event = self.put_queue[idx]
    proceed = self._do_put(put_event)
    if not put_event.triggered:
        idx += 1
    elif self.put_queue.pop(idx) != put_event:
        raise RuntimeError('Put queue invariant violated')
```

这里的不变量是：队列里只能保留尚未触发的请求。

### 最小实战

```python
queue = ["a", "b", "c"]
idx = 0
while idx < len(queue):
    item = queue[idx]
    if item == "b":
        queue.pop(idx)
    else:
        idx += 1
print(queue)
```

如果当前元素被删除，后面的元素会左移到当前位置，所以不应该递增 `idx`。如果当前元素没删除，才递增 `idx`。

### 阅读提示

循环中 `pop(idx)` 后不要再 `idx += 1`，否则会跳过后面的元素。SimPy 的资源基类正是这样处理。

“队列不变量”可以理解成：循环每一步结束后，队列必须仍然满足某个规则。SimPy 的规则是：已经触发的请求必须从等待队列中移除。

## 28. traceback、异常链和帧对象

### 定义与概念

Python 异常携带 traceback。`raise ... from None` 可以隐藏异常链。帧对象可以提供当前代码文件、函数名和行号。

traceback 是异常发生时的调用路径。普通错误里，Python 会打印从外到内的调用栈。SimPy 是调度框架，如果不处理 traceback，用户可能只看到错误发生在 `_resume()` 里，而不是自己写错的 `yield` 行。

### 语法

```python
raise RuntimeError("bad") from None

frame.f_code.co_filename
frame.f_lineno
```

异常链示例：

```python
try:
    int("abc")
except ValueError as exc:
    raise RuntimeError("parse failed") from exc
```

`from exc` 表示 RuntimeError 是由 ValueError 引起的。`from None` 则隐藏原始异常链，让错误输出更简洁。

### SimPy 场景

非法 `yield` 时，SimPy 会生成更清晰的错误位置：

```python
descr = _describe_frame(self._generator.gi_frame)
raise RuntimeError(f'\n{descr}{msg}') from None
```

进程异常时还会调整 traceback，让错误更靠近用户进程代码，而不是停在调度器内部。

### 最小实战

```python
def gen():
    frame = yield "pause"
    print(frame.f_code.co_name)


g = gen()
next(g)
try:
    g.send(g.gi_frame)
except StopIteration:
    pass
```

### 阅读提示

这是错误报告增强逻辑，不是事件调度主线。第一次读 `events.py` 时可以先跳过 `_describe_frame()`。

等你理解 `Process._resume()` 主流程后，再回来看 `_describe_frame()`，它只是为了给“yield 了非法对象”生成更好的错误信息。

## 29. time.monotonic() 和 sleep()

### 定义与概念

`time.monotonic()` 返回单调递增时间，不受系统时间调整影响。`sleep()` 暂停真实时间。

为什么不用 `time.time()`？因为系统时间可能被用户或网络校时调整，可能前进也可能后退。`monotonic()` 保证单调递增，更适合计算时间间隔。

### 语法

```python
from time import monotonic, sleep
```

### SimPy 场景

`RealtimeEnvironment.step()` 用真实时间同步仿真时间：

```python
real_time = self.real_start + (evt_time - self.env_start) * self.factor
sleep(delta)
```

### 最小实战

```python
from time import monotonic, sleep

start = monotonic()
sleep(0.1)
print(monotonic() - start)
```

### 阅读提示

普通 `Environment` 不等待真实时间。只有 `RealtimeEnvironment` 才会 `sleep()`。

所以大多数 SimPy 仿真会跑得非常快，不会按现实时间等待。`RealtimeEnvironment` 是特殊模式，适合演示或和外部真实系统同步。

## 30. SimPy 语法点总表

在进入总表前，可以用下面这张“初级语法到源码语法”的过渡表建立整体感觉：

| 你已经会的写法 | SimPy 源码中的升级写法 | 新增理解 |
| --- | --- | --- |
| 调用函数 `f(x)` | 保存函数 `callbacks.append(f)` | 函数可以作为对象传递 |
| 类实例 `obj = A()` | 动态构造 `env.timeout(5)` | `BoundClass` 把类绑定成方法 |
| `for item in list` | `while idx < len(queue)` | 遍历时要安全删除元素 |
| 普通返回 `return x` | 生成器返回触发 `StopIteration.value` | 生成器结束方式特殊 |
| 抛异常 `raise Error` | `generator.throw(Error())` | 外部可以把异常注入生成器 |
| 访问字段 `obj.x` | `@property def x(...)` | 看似字段，实际可能执行方法 |
| 字典访问 `d[key]` | `result[event]` | 自定义对象可模拟字典协议 |
| `a or b` | `event_a | event_b` | 运算符可被类重载 |
| 普通列表排序 | `heapq` 最小堆 | 只关心不断取最小事件 |
| 注释说明类型 | `Optional[T]`、`Callable` | 类型标注帮助读接口 |

| 语法点 | 位置 | 掌握要求 |
| --- | --- | --- |
| 类和对象 | 全部模块 | 必须 |
| 继承和 `super()` | 事件、资源、实时环境 | 必须 |
| `@property` | `Event`、`Environment`、资源类 | 必须 |
| 自定义异常 | `exceptions.py`、`events.py` | 必须 |
| 生成器和 `yield` | `Process`、用户进程 | 必须 |
| `send()` / `throw()` | `Process._resume()` | 必须 |
| `StopIteration` | 进程返回值 | 必须 |
| 上下文管理器 | `Put`、`Get`、`Request` | 必须 |
| 回调列表 | `Event.callbacks` | 必须 |
| `heapq` | `Environment`、`PriorityStore` | 必须 |
| 运算符重载 | `Event.__and__`、`Event.__or__` | 必须 |
| `NamedTuple` | `PriorityItem` | 应掌握 |
| `lambda` | 过滤、排序、抢占 | 应掌握 |
| 描述符 | `BoundClass` | 必须 |
| `MethodType` | `BoundClass` | 应掌握 |
| `TYPE_CHECKING` | 动态绑定方法签名 | 应掌握 |
| 泛型类型标注 | `BoundClass`、资源基类 | 能读懂即可 |
| `NewType` | 事件优先级 | 能读懂即可 |
| 帧对象和 traceback | 错误提示增强 | 了解即可 |

## 31. 常见误区纠正

### 误区 1：看到 `yield` 就以为是返回值

在普通生成器教程里，`yield` 常用于“逐个产生值”。在 SimPy 中，更重要的是“暂停进程并交出等待事件”。

```python
yield env.timeout(5)
```

不是把 timeout 当作业务结果返回，而是告诉调度器：当前进程要等这个事件。

### 误区 2：以为 `env.timeout(5)` 会真实等待 5 秒

普通 `Environment` 不等待真实时间。`env.timeout(5)` 只是创建一个仿真时间为未来 5 的事件。真实程序可能瞬间跑完整个仿真。

### 误区 3：以为 `event.succeed()` 会立刻恢复进程

`succeed()` 只是标记事件成功并放入事件队列。真正执行回调、恢复进程是在 `env.step()` 处理该事件时。

### 误区 4：以为 `callbacks = []` 和 `callbacks = None` 差不多

在 SimPy 中完全不同：

- `[]`：事件还没处理，只是暂时没有回调。
- `None`：事件已经处理完，不能再注册回调。

### 误区 5：以为 `with resource.request()` 拿到的是资源

拿到的是请求事件 `Request`，不是资源本身。它既表示“我正在申请资源”，成功后也表示“我占用了一个资源槽”。

### 误区 6：以为类型标注会限制运行时

`def f(x: int)` 不会自动禁止字符串。类型标注主要给读者和工具看。SimPy 的 `TYPE_CHECKING` 分支尤其要区分“给 IDE 看”和“运行时执行”。

### 误区 7：以为找不到方法定义就是源码缺失

`env.timeout()`、`env.process()`、`resource.request()` 这类方法很多来自 `BoundClass` 动态绑定，不一定有普通的 `def timeout(...)` 运行时定义。

## 32. 按源码文件通读

### 1. `exceptions.py`

需要掌握：

- 自定义异常。
- `super().__init__()`。
- `@property`。
- `__str__()`。

读懂目标：

- `Interrupt(cause)` 如何保存中断原因。

### 2. `events.py`

需要掌握：

- 生成器。
- `send()` / `throw()`。
- `StopIteration`。
- 回调列表。
- 运算符重载。
- 可迭代协议。
- 哨兵对象。

读懂目标：

- 事件生命周期。
- 进程如何恢复。
- 条件事件如何监听多个事件。
- 中断如何注入生成器。

### 3. `core.py`

需要掌握：

- `heapq`。
- `itertools.count()`。
- 描述符。
- `MethodType`。
- `TYPE_CHECKING`。
- 自定义异常作为控制流。

读懂目标：

- `Environment.schedule()` 如何排队事件。
- `Environment.step()` 如何处理事件。
- `Environment.run()` 如何停止。
- `env.timeout()` 为什么能创建 `Timeout(env, delay)`。

### 4. `resources/base.py`

需要掌握：

- 泛型。
- 上下文管理器。
- 类变量。
- 队列不变量。
- 回调触发。

读懂目标：

- `put/get` 请求如何入队。
- 资源状态变化后如何重新检查等待队列。
- 为什么 `with` 能自动取消未完成请求。

### 5. `resources/resource.py`

需要掌握：

- 继承。
- 排序队列。
- `max(..., key=lambda ...)`。
- 中断。

读懂目标：

- 普通资源如何申请和释放。
- 优先级资源如何排序。
- 抢占资源如何打断低优先级进程。

### 6. `resources/container.py` 和 `resources/store.py`

需要掌握：

- 子类覆盖方法。
- `NamedTuple`。
- `heapq`。
- 过滤函数。

读懂目标：

- 连续库存如何 `put/get`。
- FIFO 队列如何保存对象。
- 优先级队列如何取最小优先级对象。
- 过滤队列如何按条件匹配对象。

### 7. `rt.py` 和 `util.py`

需要掌握：

- 继承和方法覆盖。
- 内部生成器函数。
- 闭包。
- 真实时间函数。
- 中断唤醒。

读懂目标：

- 实时环境如何同步墙钟。
- `start_delayed()` 如何返回延迟启动器进程。
- `subscribe_at()` 如何用中断实现订阅。

## 33. 最小 SimPy 内核模拟

下面这个极简模型把多个语法点组合起来，只演示“生成器 yield 事件，事件完成后恢复进程”。

```python
from heapq import heappop, heappush
from itertools import count


PENDING = object()


class Event:
    def __init__(self, env):
        self.env = env
        self.callbacks = []
        self.value = PENDING

    def succeed(self, value=None):
        self.value = value
        self.env.schedule(self)
        return self


class Timeout(Event):
    def __init__(self, env, delay, value=None):
        super().__init__(env)
        self.value = value
        env.schedule(self, delay=delay)


class Process(Event):
    def __init__(self, env, generator):
        super().__init__(env)
        self.generator = generator
        env.schedule(self)

    def resume(self, event=None):
        try:
            if event is None:
                next_event = next(self.generator)
            else:
                next_event = self.generator.send(event.value)
        except StopIteration as exc:
            self.value = exc.value
            for callback in self.callbacks:
                callback(self)
            return

        next_event.callbacks.append(self.resume)


class Environment:
    def __init__(self):
        self.now = 0
        self.queue = []
        self.eid = count()

    def timeout(self, delay, value=None):
        return Timeout(self, delay, value)

    def process(self, generator):
        proc = Process(self, generator)
        proc.callbacks.append(lambda event: None)
        return proc

    def schedule(self, event, delay=0):
        heappush(self.queue, (self.now + delay, next(self.eid), event))

    def run(self):
        while self.queue:
            self.now, _, event = heappop(self.queue)
            if isinstance(event, Process) and event.value is PENDING:
                event.resume()
            else:
                callbacks, event.callbacks = event.callbacks, None
                for callback in callbacks:
                    callback(event)


def car(env):
    print(env.now, "start")
    result = yield env.timeout(5, value="done")
    print(env.now, result)


env = Environment()
env.process(car(env))
env.run()
```

对应 SimPy 源码：

| 极简代码 | SimPy 源码 |
| --- | --- |
| `Environment.queue` | `Environment._queue` |
| `Timeout` | `simpy.events.Timeout` |
| `Process.resume()` | `Process._resume()` |
| `callbacks` | `Event.callbacks` |
| `heappush/heappop` | `Environment.schedule()` / `step()` |
| `generator.send()` | `Process._resume()` |

## 34. 通读前检查清单

如果下面这些问题都能回答，就具备通读 SimPy 源码的语法基础：

- 为什么 `env.timeout(5)` 没有在 `Environment` 中定义成普通方法？
- 为什么 `yield env.timeout(5)` 能暂停进程？
- 为什么事件成功值会成为 `yield` 表达式的返回值？
- 为什么进程 `return value` 会变成 `Process.value`？
- 为什么中断能在 `yield` 处变成 `simpy.Interrupt` 异常？
- 为什么 `with resource.request() as req:` 能防止资源泄漏？
- 为什么 `event.callbacks is None` 表示事件已经处理完？
- 为什么事件队列用 `(time, priority, eid, event)` 元组？
- 为什么 `req | timeout` 能构造条件事件？
- 为什么 `PriorityStore` 的对象需要能比较？
- 为什么 `TYPE_CHECKING` 分支看起来有方法实现，但运行时走的是 `BoundClass`？
- 为什么 `BaseResource` 用 `PutQueue` 类变量控制子类队列行为？

## 35. 建议练习

1. 手写一个只支持 `timeout()` 的最小环境。
2. 给最小环境加 `Process`，支持 `yield process` 等待子进程。
3. 给事件加 `fail()`，用 `generator.throw()` 把异常送回进程。
4. 写一个 `Resource`，支持 `request()` 和 `release()`。
5. 给 `request()` 加 `__enter__()` 和 `__exit__()`。
6. 给事件实现 `__or__()`，支持等待任意一个事件。
7. 用 `heapq` 实现按优先级调度。
8. 实现一个简化版 `BoundClass`，让 `env.timeout(1)` 等价于 `Timeout(env, 1)`。

这些练习完成后，再回到 SimPy 源码，核心逻辑基本都能对应上。
