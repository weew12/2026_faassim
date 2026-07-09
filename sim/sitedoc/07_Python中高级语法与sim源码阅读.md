# 07. Python 中高级语法与 sim 源码阅读

这份文档面向 `sim` 包源码阅读者。它不是普通 Python 教程，而是围绕 faas-sim 的业务仿真层，解释源码中真正出现的 Python 中高级语法。

如果说 `simpy` 包解决的是“事件如何调度”，那么 `sim` 包解决的是“FaaS 平台业务如何映射成事件、进程、资源、指标和调度对象”。

读完本文后，应能通读这些文件：

- `sim/faas/core.py`
- `sim/faas/system.py`
- `sim/faas/watchdogs.py`
- `sim/faas/scaling.py`
- `sim/core.py`
- `sim/faassim.py`
- `sim/benchmark.py`
- `sim/requestgen.py`
- `sim/resource.py`
- `sim/metrics.py`
- `sim/logging.py`
- `sim/docker.py`
- `sim/skippy.py`
- `sim/topology.py`
- `sim/oracle/oracle.py`

## 0. sim 与 simpy 的区别

`simpy` 是底层离散事件仿真库。它提供：

- `Environment`
- `Event`
- `Process`
- `Resource`
- `Store`
- `Container`
- `yield env.timeout(...)`

`sim` 是业务层。它使用 SimPy 来描述 FaaS 平台：

- 函数定义、镜像、容器、副本、请求。
- 函数部署、启动、调用、删除、扩缩容。
- 调度队列、负载均衡、资源监控、指标记录。
- 启动时间、执行时间、带宽、成本和资源利用率 Oracle。

所以读 `sim` 时，核心问题不是“事件队列怎么实现”，而是：

```text
业务对象 -> SimPy 进程 -> 仿真时间推进 -> 指标记录
```

一个典型片段：

```python
def deploy(self, fd):
    self.env.metrics.log_function_deployment(fd)
    yield from self.scale_up(fd.name, fd.scaling_config.scale_min)
```

这里同时涉及：

- 方法和对象状态。
- 结构化指标记录。
- 生成器协程。
- `yield from` 把子流程接到当前流程。
- 伸缩逻辑产生新的副本和调度事件。

## 1. 从业务对象开始读源码

### 定义与概念

`sim` 包大量代码不是算法，而是业务模型。业务模型通常由类表达。读这类代码时，先不要急着看每个方法细节，先建立对象关系。

FaaS 领域对象大致是：

| 对象 | 含义 |
| --- | --- |
| `Function` | 一个函数定义，包含名称、镜像集合、标签 |
| `FunctionImage` | 某个函数可用的镜像标识 |
| `FunctionContainer` | 镜像 + 资源请求 + 标签，是副本模板 |
| `FunctionDeployment` | 一个完整函数部署，包含函数、容器、伸缩配置 |
| `FunctionReplica` | 实际运行副本，有节点、Pod、状态、模拟器 |
| `FunctionRequest` | 一次函数调用请求 |
| `FunctionResponse` | 一次调用响应结果 |
| `DefaultFaasSystem` | 默认 FaaS 平台实现 |

### 语法

```python
class Function:
    def __init__(self, name, fn_images, labels=None):
        self.name = name
        self.fn_images = fn_images
        self.labels = labels if labels is not None else {}
```

这就是典型业务对象类：接收外部参数，写入对象字段。

### sim 场景

`sim/faas/core.py` 中，`FunctionDeployment` 把多个对象组合起来：

```python
class FunctionDeployment:
    def __init__(self, fn, fn_containers, scaling_config, deployment_ranking=None):
        self.fn = fn
        self.fn_containers = fn_containers
        self.scaling_config = scaling_config
```

这说明部署不是单个字符串，而是一个聚合对象。

### 最小实战

```python
class Function:
    def __init__(self, name):
        self.name = name


class FunctionDeployment:
    def __init__(self, fn, scale_min=1):
        self.fn = fn
        self.scale_min = scale_min

    @property
    def name(self):
        return self.fn.name


fn = Function("resize")
deployment = FunctionDeployment(fn, scale_min=2)
print(deployment.name, deployment.scale_min)
```

### 阅读提示

读 `sim/faas/core.py` 时，先画对象关系，而不是逐行读：

```text
Function
  -> FunctionImage
  -> FunctionContainer
  -> FunctionDeployment
      -> FunctionReplica
      -> FunctionRequest
```

## 2. 类型标注是业务说明，不是运行时约束

### 定义与概念

`sim` 源码里有很多类型标注：

```python
fn_containers: List[FunctionContainer]
labels: Dict[str, str]
state: FunctionState = FunctionState.CONCEIVED
```

这些标注帮助你理解字段含义，但 Python 默认不会在运行时强制检查。

### 语法

```python
from typing import List, Dict, Optional, Tuple

def get_container(image: str) -> Optional[FunctionContainer]:
    ...
```

含义：

- `List[T]`：元素类型为 `T` 的列表。
- `Dict[K, V]`：键类型为 `K`、值类型为 `V` 的字典。
- `Optional[T]`：可能是 `T`，也可能是 `None`。
- `Tuple[A, B]`：二元组，第一项是 `A`，第二项是 `B`。

### sim 场景

`Function.get_image()`：

```python
def get_image(self, image: str) -> Optional[FunctionImage]:
    for fn_image in self.fn_images:
        if fn_image.image == image:
            return fn_image
    return None
```

`Optional[FunctionImage]` 提醒你：调用方必须处理找不到镜像的情况。

### 最小实战

```python
from typing import Optional


class Image:
    def __init__(self, name):
        self.name = name


def find_image(images, name: str) -> Optional[Image]:
    for image in images:
        if image.name == name:
            return image
    return None


result = find_image([Image("a")], "b")
if result is None:
    print("not found")
```

### 阅读提示

类型标注可以当作“轻量文档”。初读源码时，先看标注理解数据形状，再看方法体理解控制流。

## 3. Enum：状态机的可读表达

### 定义与概念

`Enum` 用于定义一组固定状态。相比直接用整数或字符串，枚举更清晰，也更不容易拼错。

### 语法

```python
import enum


class State(enum.Enum):
    STARTING = 1
    RUNNING = 2
    STOPPED = 3
```

### sim 场景

`FunctionState`：

```python
class FunctionState(enum.Enum):
    CONCEIVED = 1
    STARTING = 2
    RUNNING = 3
    SUSPENDED = 4
```

副本生命周期用它表达：

```python
replica.state = FunctionState.RUNNING
```

筛选运行副本时：

```python
replica.state == FunctionState.RUNNING
```

### 最小实战

```python
import enum


class FunctionState(enum.Enum):
    CONCEIVED = 1
    RUNNING = 2


state = FunctionState.CONCEIVED
if state == FunctionState.CONCEIVED:
    print("not ready")
```

### 阅读提示

读 `DefaultFaasSystem.invoke()` 时，看到 `FunctionState.RUNNING` 就要理解：只有运行态副本才能承接请求。

## 4. @property：业务字段转发

### 定义与概念

`@property` 把方法伪装成属性。`sim` 中常用于把嵌套对象字段转发成更好用的属性。

### 语法

```python
class A:
    @property
    def name(self):
        return "value"
```

调用：

```python
a.name
```

### sim 场景

`FunctionDeployment.name`：

```python
@property
def name(self):
    return self.fn.name
```

`FunctionReplica.image`：

```python
@property
def image(self):
    return self.container.image
```

这让业务代码可以写：

```python
deployment.name
replica.image
```

而不必写：

```python
deployment.fn.name
replica.container.image
```

### 最小实战

```python
class Container:
    def __init__(self, image):
        self.image = image


class Replica:
    def __init__(self, container):
        self.container = container

    @property
    def image(self):
        return self.container.image


replica = Replica(Container("fn:v1"))
print(replica.image)
```

### 阅读提示

`@property` 经常隐藏了一层对象跳转。读源码时看到 `replica.image`，要知道它实际来自 `replica.container.image`。

## 5. NamedTuple：轻量不可变记录

### 定义与概念

`NamedTuple` 是有字段名的元组。适合表示结构简单、创建后不怎么修改的数据记录。

### 语法

两种写法都在 `sim` 中出现：

```python
from typing import NamedTuple


class Record(NamedTuple):
    measurement: str
    fields: dict
```

函数式写法：

```python
Bandwidth = NamedTuple("Bandwidth", [("mbit", int), ("delay", int)])
```

### sim 场景

`sim/logging.py`：

```python
class Record(NamedTuple):
    measurement: str
    time: int
    fields: Dict
    tags: Dict
```

`sim/oracle/oracle.py`：

```python
Bandwidth = NamedTuple('Bandwidth', [('mbit', int), ('delay', int), ('deviation', int)])
```

### 最小实战

```python
from typing import NamedTuple


class Record(NamedTuple):
    measurement: str
    value: float


record = Record("cpu", 0.7)
print(record.measurement)
print(record[1])
```

### 阅读提示

`NamedTuple` 可以用点访问，也可以像元组一样用下标访问和解包。它通常不用于频繁修改状态。

## 6. dataclass：自动生成初始化方法

### 定义与概念

`@dataclass` 可以自动生成 `__init__()`、`__repr__()` 等方法，适合纯数据对象。

### 语法

```python
from dataclasses import dataclass


@dataclass
class Window:
    start: float
    end: float
```

### sim 场景

`sim/resource.py` 中的 `ResourceWindow`：

```python
@dataclass
class ResourceWindow:
    replica: FunctionReplica
    window_start: float
    window_end: float
    resources: Dict[str, float]
```

这类对象主要用于保存一个时间窗口内的资源采样。

### 最小实战

```python
from dataclasses import dataclass


@dataclass
class ResourceWindow:
    start: float
    end: float
    cpu: float


window = ResourceWindow(0, 10, 0.5)
print(window)
```

### 阅读提示

看到 `@dataclass` 但没有 `__init__()`，不要以为对象不能初始化。初始化方法是 dataclass 自动生成的。

## 7. 双下划线字段：名称改写

### 定义与概念

单下划线 `_name` 是内部约定；双下划线 `__name` 会触发 Python 名称改写，避免子类意外覆盖。

### 语法

```python
class A:
    def __init__(self):
        self.__value = 1
```

真实保存名大致会变成：

```text
_A__value
```

### sim 场景

`ResourceUtilization`：

```python
self.__resources = {}
```

`NodeResourceUtilization`：

```python
self.__resources = {}
self.__replicas = {}
```

这些字段是内部状态，外部应通过方法访问：

```python
put_resource()
remove_resource()
list_resources()
get_resource()
```

### 最小实战

```python
class Store:
    def __init__(self):
        self.__items = []

    def add(self, item):
        self.__items.append(item)

    def list_items(self):
        return list(self.__items)


store = Store()
store.add("a")
print(store.list_items())
print(store.__dict__)
```

### 阅读提示

双下划线不是安全机制，只是名称改写。读源码时知道它表示“作者不希望外部直接动这个字段”即可。

## 8. 魔术方法：让对象像容器、字符串或调试记录

### 定义与概念

魔术方法是双下划线方法，会被 Python 语法自动调用。

| 方法 | 触发语法 |
| --- | --- |
| `__str__` | `str(obj)`、`print(obj)` |
| `__repr__` | 交互式显示、列表中显示对象 |
| `__len__` | `len(obj)` |
| `__getitem__` | `obj[key]` |
| `__setitem__` | `obj[key] = value` |
| `__delitem__` | `del obj[key]` |

### sim 场景

`FunctionResourceCharacterization`：

```python
def __getitem__(self, key):
    return self.__getattribute__(key)

def __setitem__(self, key, value):
    self.__setattr__(key, value)
```

这让资源画像既能按属性访问：

```python
profile.cpu
```

也能按字典风格访问：

```python
profile["cpu"]
```

### 最小实战

```python
class Resources:
    def __init__(self, cpu, ram):
        self.cpu = cpu
        self.ram = ram

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __len__(self):
        return 2


r = Resources(1.0, 512)
print(r["cpu"])
r["ram"] = 1024
print(r.ram, len(r))
```

### 阅读提示

看到 `obj["cpu"]` 时，不一定是字典。先看对象类是否实现了 `__getitem__()`。

## 9. abc.ABC 与抽象接口

### 定义与概念

`abc.ABC` 用于定义抽象基类。抽象基类表达“子类必须提供这些方法”。它适合定义平台接口、模拟器接口、资源配置接口。

### 语法

```python
import abc


class Service(abc.ABC):
    @abc.abstractmethod
    def run(self):
        ...
```

### sim 场景

`FaasSystem`：

```python
class FaasSystem(abc.ABC):
    @abc.abstractmethod
    def deploy(self, fn): ...

    @abc.abstractmethod
    def invoke(self, request): ...
```

`DefaultFaasSystem` 继承它并实现具体逻辑。

`FunctionSimulator` 也定义了部署、启动、setup、调用、teardown 等生命周期接口。

### 最小实战

```python
import abc


class Simulator(abc.ABC):
    @abc.abstractmethod
    def invoke(self):
        ...


class DummySimulator(Simulator):
    def invoke(self):
        print("invoke")


sim = DummySimulator()
sim.invoke()
```

### 阅读提示

抽象方法里只有 `...` 不代表忘写了，而是表示“这里是接口，具体实现看子类”。

## 10. 继承、Mixin 和方法解析顺序

### 定义与概念

Mixin 是一种只提供部分能力的类，通常不单独使用，而是和其他类组合成完整类。

### 语法

```python
class A:
    def run(self):
        print("A")


class B:
    def setup(self):
        print("B")


class C(B, A):
    pass
```

### sim 场景

`sim/faassim.py` 中：

```python
class SimpleFunctionSimulator(ModeledExecutionSimMixin, DockerDeploySimMixin, DummySimulator):
    pass
```

含义：

- `DockerDeploySimMixin` 提供镜像拉取部署逻辑。
- `ModeledExecutionSimMixin` 提供按模型执行函数的逻辑。
- `DummySimulator` 提供默认的空生命周期方法。

Python 会按 MRO 查找方法，前面的类优先。

### 最小实战

```python
class Base:
    def deploy(self):
        print("base deploy")


class DockerMixin:
    def deploy(self):
        print("docker deploy")


class Simulator(DockerMixin, Base):
    pass


Simulator().deploy()
print([cls.__name__ for cls in Simulator.mro()])
```

### 阅读提示

读多继承类时，一定要看继承顺序。`SimpleFunctionSimulator.invoke()` 来自 `ModeledExecutionSimMixin`，`deploy()` 来自 `DockerDeploySimMixin`，其他没覆盖的方法来自 `DummySimulator`。

## 11. yield from：串联业务协程

### 定义与概念

`yield from sub_generator` 表示把子生成器产生的所有事件交给外层生成器。它适合把一个长流程拆成多个子流程。

### 语法

```python
def child():
    yield "a"
    yield "b"


def parent():
    yield from child()
    yield "c"
```

### sim 场景

`DefaultFaasSystem.deploy()`：

```python
yield from self.scale_up(fd.name, fd.scaling_config.scale_min)
```

`simulate_function_start()`：

```python
yield from sim.deploy(env, replica)
yield from sim.startup(env, replica)
yield from sim.setup(env, replica)
```

这表达一个业务生命周期：

```text
部署镜像 -> 启动容器 -> setup -> 副本可运行
```

### 最小实战

```python
def pull_image():
    print("pull")
    yield "wait-pull"


def start_container():
    print("start")
    yield "wait-start"


def lifecycle():
    yield from pull_image()
    yield from start_container()
    print("ready")


g = lifecycle()
print(next(g))
print(next(g))
try:
    next(g)
except StopIteration:
    print("done")
```

### 阅读提示

在 `sim` 中，`yield from` 常常表示“当前业务流程要完整等待子业务流程结束”。不要把它理解成普通函数调用。

## 12. env.process：并发启动业务进程

### 定义与概念

`env.process(generator)` 把生成器交给 SimPy 环境调度。它不会像 `yield from` 那样把子流程嵌入当前流程，而是启动一个可并发运行的 SimPy 进程。

### 语法

```python
env.process(worker())
```

### sim 场景

请求生成器里：

```python
env.process(env.faas.invoke(FunctionRequest(deployment.name)))
```

这表示每个请求独立启动一个调用进程。请求生成器自己继续等待下一个到达间隔。

伸缩器里：

```python
self.env.process(self.faas_scalers[fd.name].run())
```

这表示后台伸缩器常驻运行。

### 最小实战

```python
import simpy


def job(env, name):
    print(env.now, name, "start")
    yield env.timeout(1)
    print(env.now, name, "done")


def source(env):
    env.process(job(env, "a"))
    env.process(job(env, "b"))
    yield env.timeout(2)


env = simpy.Environment()
env.process(source(env))
env.run()
```

### 阅读提示

对比：

- `yield from child()`：当前流程等待 child 完成。
- `env.process(child())`：启动 child，当前流程可以继续。
- `yield env.process(child())`：启动 child，并等待 child 完成。

## 13. SimPy Store：业务队列

### 定义与概念

`simpy.Store` 是离散对象队列。业务层常用它保存请求、副本调度任务等对象。

### 语法

```python
store = simpy.Store(env)
yield store.put(item)
item = yield store.get()
```

### sim 场景

`DefaultFaasSystem.__init__()`：

```python
self.request_queue = simpy.Store(env)
self.scheduler_queue = simpy.Store(env)
```

部署副本时：

```python
yield self.scheduler_queue.put((replica, services))
```

调度 worker 中：

```python
replica, services = yield self.scheduler_queue.get()
```

### 最小实战

```python
import simpy


def producer(env, queue):
    yield queue.put(("replica-1", ["svc-a"]))


def worker(env, queue):
    replica, services = yield queue.get()
    print(env.now, replica, services)


env = simpy.Environment()
queue = simpy.Store(env)
env.process(worker(env, queue))
env.process(producer(env, queue))
env.run()
```

### 阅读提示

`Store` 里的对象可以是任意 Python 对象。`scheduler_queue` 中保存的是 `(replica, services)` 元组，不是简单字符串。

## 14. defaultdict：自动创建默认值

### 定义与概念

`defaultdict(factory)` 是字典增强版。访问不存在的键时，会自动调用 `factory` 创建默认值。

### 语法

```python
from collections import defaultdict

d = defaultdict(list)
d["a"].append(1)
```

普通 dict 中 `d["a"]` 会报 `KeyError`；`defaultdict(list)` 会自动创建空列表。

### sim 场景

`DefaultFaasSystem`：

```python
self.replicas = defaultdict(list)
```

这样可以直接：

```python
self.replicas[fd.name].append(replica)
```

`Metrics`：

```python
self.utilization = defaultdict(lambda: defaultdict(float))
```

这是嵌套默认字典。

### 最小实战

```python
from collections import defaultdict

replicas = defaultdict(list)
replicas["resize"].append("replica-1")
print(replicas)

util = defaultdict(lambda: defaultdict(float))
util["node-a"]["cpu"] += 0.5
print(util["node-a"]["cpu"])
```

### 阅读提示

看到 `defaultdict(lambda: defaultdict(float))` 时，可以理解成“两层字典，内层默认值是 0.0”。

## 15. Counter：计数器字典

### 定义与概念

`Counter` 是专门用于计数的字典。不存在的键默认计数为 0。

### 语法

```python
from collections import Counter

c = Counter()
c["fn"] += 1
```

### sim 场景

`DefaultFaasSystem`：

```python
self.functions_definitions = Counter()
```

用于统计函数定义引用或部署相关数量。

### 最小实战

```python
from collections import Counter

counter = Counter()
counter["resize"] += 1
counter["resize"] += 1
counter["classify"] += 1
print(counter)
```

### 阅读提示

`Counter` 适合表示“某类对象出现了几次”。它比手动 `dict.get(key, 0) + 1` 更清楚。

## 16. list/dict 推导式、map 和 lambda

### 定义与概念

推导式用于从一个集合快速构造另一个集合。`map()` 会把函数应用到每个元素。`lambda` 是短函数。

### 语法

```python
names = [item.name for item in items]
mapping = {item.name: item for item in items}
result = list(map(lambda x: x * 2, [1, 2, 3]))
```

### sim 场景

`FunctionDeployment`：

```python
DeploymentRanking([x.image for x in self.fn.fn_images])
```

```python
def get_services(self):
    return list(map(lambda image: self.fn.get_image(image), self.ranking.images))
```

`DefaultFaasSystem.get_replicas()`：

```python
return [replica for replica in self.replicas[fn_name] if replica.state == state]
```

### 最小实战

```python
class Image:
    def __init__(self, image):
        self.image = image


images = [Image("a"), Image("b")]
names = [x.image for x in images]
print(names)

selected = list(map(lambda name: name.upper(), names))
print(selected)
```

### 阅读提示

推导式从左到右读：

```python
[表达式 for 元素 in 集合 if 条件]
```

先找到 `for`，再看每个元素如何被转换。

## 17. 生成器作为无限数据源

### 定义与概念

生成器可以无限产生值。`sim` 中请求 ID、RPS 曲线、到达间隔都使用生成器。

### 语法

```python
def counter(start=1):
    n = start
    while True:
        yield n
        n += 1
```

### sim 场景

`FunctionRequest.id_generator`：

```python
id_generator = counter()
```

创建请求时：

```python
self.request_id = next(self.id_generator)
```

请求速率 profile：

```python
def constant_rps_profile(rps):
    while True:
        yield rps
```

### 最小实战

```python
def counter(start=1):
    n = start
    while True:
        yield n
        n += 1


ids = counter()
print(next(ids))
print(next(ids))
print(next(ids))
```

### 阅读提示

看到 `next(generator)`，表示从生成器取下一个值。这个值可能是请求 ID，也可能是下一段到达间隔。

## 18. try/except：仿真流程的边界处理

### 定义与概念

仿真中某些进程是长期运行的。如果外部中断它，代码需要捕获 `simpy.Interrupt` 并退出。

### 语法

```python
try:
    ...
except SomeError:
    ...
```

### sim 场景

`function_trigger()`：

```python
try:
    ...
except simpy.Interrupt:
    pass
except StopIteration:
    logging.error(...)
```

含义：

- 被中断：安静退出请求生成。
- 到达间隔生成器耗尽：记录错误。

### 最小实战

```python
class Interrupt(Exception):
    pass


def trigger(gen):
    try:
        while True:
            print(next(gen))
    except StopIteration:
        print("generator finished")


trigger(iter([1, 2, 3]))
```

### 阅读提示

在长期运行进程中，`except simpy.Interrupt: pass` 通常是“收到停止信号后退出”，不是吞掉普通错误。

## 19. logging：模块级日志器

### 定义与概念

Python 标准库 `logging` 用于记录运行日志。相比 `print()`，日志可以设置级别、模块名和输出格式。

### 语法

```python
import logging

logger = logging.getLogger(__name__)
logger.info("message %s", name)
```

### sim 场景

很多模块顶部都有：

```python
logger = logging.getLogger(__name__)
```

调用时：

```python
logger.info('deploying function %s', fd.name)
logger.warning('invoking non-existing function %s', request.name)
logger.debug('dispatching request %s', request.name)
```

### 最小实战

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("deploying %s", "resize")
```

### 阅读提示

日志参数通常用 `%s` 占位，而不是 f-string。这是 logging 推荐写法：如果日志级别没启用，可以避免提前格式化字符串。

## 20. 结构化日志：Record 与 RuntimeLogger

### 定义与概念

结构化日志不是普通文本，而是带 measurement、time、fields、tags 的记录。后续可以转成 DataFrame 或导入时序数据库。

### sim 场景

`Record`：

```python
class Record(NamedTuple):
    measurement: str
    time: int
    fields: Dict
    tags: Dict
```

`RuntimeLogger.log()`：

```python
if type(value) == dict:
    fields = value
else:
    fields = {'value': value}
```

这允许记录两类数据：

```python
log("cpu", 0.7, node="n1")
log("invocation", {"wait": 1.2, "exec": 3.4}, function="resize")
```

### 最小实战

```python
from typing import NamedTuple


class Record(NamedTuple):
    measurement: str
    fields: dict
    tags: dict


def log(metric, value, **tags):
    fields = value if type(value) == dict else {"value": value}
    return Record(metric, fields, tags)


print(log("cpu", 0.5, node="n1"))
print(log("invocation", {"wait": 1, "exec": 2}, fn="resize"))
```

### 阅读提示

`**tags` 表示接收任意关键字参数并收集成字典。调用 `log(metric, value, node="n1")` 时，`tags` 是 `{"node": "n1"}`。

## 21. *args 与 **kwargs

### 定义与概念

`*args` 接收任意位置参数，`**kwargs` 接收任意关键字参数。`sim` 中更多使用 `**kwargs` 做指标标签透传。

### 语法

```python
def f(*args, **kwargs):
    print(args)
    print(kwargs)
```

### sim 场景

`Metrics.log_invocation()`、`log_start_exec()` 等方法中有：

```python
def log_invocation(function_name, node_name, **kwargs):
    ...
```

这允许调用方附加额外标签或字段，而不用频繁改函数签名。

### 最小实战

```python
def log(metric, value, **tags):
    print(metric, value, tags)


log("cpu", 0.8, node="n1", function="resize")
```

### 阅读提示

看到 `**kwargs` 时，要追踪它是否被继续传给别的函数。它常用于“保留扩展口”。

## 22. 文件读写、pickle 和 with

### 定义与概念

`with open(...)` 用上下文管理器打开文件，退出时自动关闭。`pickle` 用于保存和加载 Python 对象。

### 语法

```python
with open(file, "wb") as fd:
    pickle.dump(obj, fd)
```

### sim 场景

`pre_recorded_profile()`：

```python
def pre_recorded_profile(file):
    with open(file, 'rb') as fd:
        yield from pickle.load(fd)
```

`save_requests()`：

```python
with open(file, 'wb') as fd:
    pickle.dump(ias, fd)
```

### 最小实战

```python
import pickle
import tempfile

data = [1, 2, 3]

with tempfile.NamedTemporaryFile(delete=False) as fd:
    pickle.dump(data, fd)
    name = fd.name

with open(name, "rb") as fd:
    loaded = pickle.load(fd)

print(loaded)
```

### 阅读提示

`pickle` 适合保存 Python 内部实验数据，不适合不可信输入。不要随便加载来源不明的 pickle 文件。

## 23. Pandas DataFrame：实验数据处理

### 定义与概念

Pandas 用表格处理实验数据。`DataFrame` 类似带列名的数据表。

### 语法

```python
import pandas as pd

df = pd.DataFrame({"time": [0, 1], "value": [3, 4]})
```

### sim 场景

`run_arrival_profile()`：

```python
df = pd.DataFrame(data={'simtime': x, 'ia': y}, index=pd.DatetimeIndex(...))
```

`EmpiricalOracle`：

```python
dfs = [pd.read_csv(filename) for filename in csvs]
df = pd.concat(dfs)
df = df.loc[df['status'].isin(['passed'])]
```

### 最小实战

```python
import pandas as pd

df = pd.DataFrame({"simtime": [0, 1, 2], "ia": [0.2, 0.4, 0.3]})
print(df["ia"].mean())
print(df.loc[df["ia"] > 0.25])
```

### 阅读提示

读 Pandas 代码时先找数据列。`df['status'].isin(['passed'])` 是布尔筛选，`df.loc[...]` 用筛选结果取行。

## 24. Numpy：数值数组和统计

### 定义与概念

Numpy 用于数值数组和统计计算。`sim` 中用于资源向量、退化模型输入、均值/标准差/百分位。

### 语法

```python
import numpy as np

x = np.array([1, 2, 3])
print(np.mean(x))
```

### sim 场景

`degradation.py`：

```python
mean = np.mean(sums[resource])
std = np.std(sums[resource])
p_50 = np.percentile(sums[resource], q=0.5)
```

`core.py` 中模型输入 reshape：

```python
x = np.array(x).reshape((1, -1))
```

### 最小实战

```python
import numpy as np

values = np.array([1, 2, 3, 4])
print(np.mean(values))
print(np.std(values))
print(values.reshape((1, -1)))
```

### 阅读提示

`reshape((1, -1))` 表示变成 1 行，列数自动推断。机器学习模型常要求输入是二维数组。

## 25. eval 与 literal_eval：字符串转对象

### 定义与概念

`eval()` 会执行字符串中的 Python 表达式，风险很高。`ast.literal_eval()` 只解析安全的字面量，如元组、列表、字典、数字、字符串。

### sim 场景

`oracle.py` 中：

```python
from ast import literal_eval as make_tuple
df['host'] = df['host'].apply(lambda x: make_tuple(x)[0][:-1])
```

同文件中也有：

```python
df['bandwidth'] = df['bandwidth'].apply(lambda x: eval(x))
```

这表示源码把 CSV 中的字符串字段还原成 Python 对象。`literal_eval` 更安全；`eval` 需要确保输入可信。

### 最小实战

```python
from ast import literal_eval

text = "('node_a', 1)"
value = literal_eval(text)
print(value[0])
```

### 阅读提示

看到 `eval()` 要保持警惕。它不是普通解析，会执行代码。实验数据来自可信本地文件时风险较小，但文档和工程中应明确输入边界。

## 26. 字符串格式化

### 定义与概念

源码中混用了 `%` 格式化、`str.format()`、f-string 和 logging 占位。

### 语法

```python
"name=%s" % name
"name={}".format(name)
f"name={name}"
logger.info("name=%s", name)
```

### sim 场景

`FunctionRequest.__str__()`：

```python
def request_text(self):
    return 'FunctionRequest(%d, %s, %s)' % (self.request_id, self.name, self.size)
```

`Resources.__str__()`：

```python
def resources_text(self):
    return 'Resources(CPU: {0} Memory: {1})'.format(self.cpu, self.memory)
```

`requestgen.py`：

```python
logging.error(f'{deployment.name} gen has finished')
```

### 最小实战

```python
name = "resize"
request_id = 3

print("FunctionRequest(%d, %s)" % (request_id, name))
print("FunctionRequest({}, {})".format(request_id, name))
print(f"FunctionRequest({request_id}, {name})")
```

### 阅读提示

logging 中推荐：

```python
logger.info("function %s", name)
```

而不是：

```python
logger.info(f"function {name}")
```

因为前者可以延迟格式化。

## 27. 静态方法 @staticmethod

### 定义与概念

`@staticmethod` 定义不依赖 `self` 的类内函数。它放在类里只是因为语义上属于这个类。

### 语法

```python
class A:
    @staticmethod
    def create(x):
        return A(x)
```

### sim 场景

`Resources.from_str()`：

```python
@staticmethod
def from_str(memory, cpu):
    return Resources(int(cpu.rstrip('m')), parse_size_string(memory))
```

`KubernetesResourceConfiguration.create_from_str()`：

```python
@staticmethod
def create_from_str(cpu: str, memory: str):
    return KubernetesResourceConfiguration(Resources.from_str(memory, cpu))
```

### 最小实战

```python
class Resources:
    def __init__(self, cpu):
        self.cpu = cpu

    @staticmethod
    def from_millis(text):
        return Resources(int(text.rstrip("m")))


r = Resources.from_millis("500m")
print(r.cpu)
```

### 阅读提示

静态方法通常是“构造辅助函数”或“格式转换函数”。它不读取当前对象状态。

## 28. 模块导出 __all__

### 定义与概念

`__all__` 控制 `from module import *` 时导出哪些名字。

### 语法

```python
__all__ = ["public_func"]
```

### sim 场景

`requestgen.py`：

```python
__all__ = [
    'constant_rps_profile',
    'sine_rps_profile',
    ...
]
```

### 最小实战

```python
# mymodule.py
__all__ = ["a"]

a = 1
b = 2
```

`from mymodule import *` 只导入 `a`。

### 阅读提示

`__all__` 是模块 API 边界提示。它告诉你哪些函数更可能是给外部使用的。

## 29. 外部系统适配：对象转换函数

### 定义与概念

业务仿真层经常需要把内部对象转换成外部库需要的对象。`sim/skippy.py` 就是 faas-sim 与 Skippy 调度器之间的适配层。

### 语法

```python
def to_external(internal):
    external = External()
    external.name = internal.name
    return external
```

### sim 场景

`create_function_pod()` 把 `FunctionDeployment` 和 `FunctionContainer` 转成 Skippy `Pod`。

`to_skippy_node()` 把 Ether 节点转成 Skippy 节点。

### 最小实战

```python
class InternalNode:
    def __init__(self, name, arch):
        self.name = name
        self.arch = arch


class SchedulerNode:
    def __init__(self, name, labels):
        self.name = name
        self.labels = labels


def to_scheduler_node(node):
    return SchedulerNode(node.name, {"arch": node.arch})


print(to_scheduler_node(InternalNode("n1", "x86")).labels)
```

### 阅读提示

适配层通常字段很多，但逻辑不一定复杂。读时重点看“内部对象哪个字段映射到外部对象哪个字段”。

## 30. Oracle 模式：统一接口，多种估计实现

### 定义与概念

Oracle 在这里表示“估计器”。不同 Oracle 都提供 `estimate(...)`，但估计内容不同：启动时间、执行时间、带宽、成本、资源利用率。

### 语法

```python
class Oracle:
    def estimate(self, context, pod, scheduling_result):
        raise NotImplementedError
```

### sim 场景

```text
class StartupTimeOracle(EmpiricalOracle):
    def estimate(...):
        return 'startup_time', str(startup_time)


class CostOracle(Oracle):
    def estimate(...):
        return 'cost', str(cost)
```

返回值通常是：

```text
(指标名, 指标值)
```

### 最小实战

```python
class Oracle:
    def estimate(self, x):
        raise NotImplementedError


class DoubleOracle(Oracle):
    def estimate(self, x):
        return "double", x * 2


oracle = DoubleOracle()
print(oracle.estimate(3))
```

### 阅读提示

读 Oracle 时，不要只看父类。父类定义接口，真正估计逻辑在子类。

## 31. sim 源码语法点总表

| 语法点 | 位置 | 必须程度 |
| --- | --- | --- |
| 类和对象组合 | `faas/core.py` | 必须 |
| 类型标注 | 全部模块 | 必须能读 |
| `Enum` | `FunctionState` | 必须 |
| `@property` | Deployment、Replica、Metrics | 必须 |
| `NamedTuple` | logging、oracle、response | 必须 |
| `@dataclass` | `ResourceWindow` | 应掌握 |
| 双下划线字段 | resource 状态类 | 应掌握 |
| 魔术方法 | resource characterization、request | 必须 |
| ABC 抽象接口 | FaasSystem、Simulator、ResourceConfiguration | 必须 |
| Mixin 多继承 | simulator 组合 | 必须 |
| `yield from` | 部署、调用、生命周期 | 必须 |
| `env.process` | 请求生成、后台伸缩器 | 必须 |
| `simpy.Store` | scheduler_queue、request_queue | 必须 |
| `defaultdict` | replicas、metrics、registry | 必须 |
| `Counter` | function definitions | 应掌握 |
| 推导式 / lambda / map | 镜像排序、筛选 | 必须 |
| 无限生成器 | 请求 ID、RPS、到达间隔 | 必须 |
| try/except | 长期进程边界 | 必须 |
| logging | 模块日志 | 应掌握 |
| `**kwargs` | 指标标签扩展 | 应掌握 |
| pickle / with | 请求序列保存 | 了解 |
| Pandas / Numpy | Oracle、metrics、degradation | 应掌握 |
| eval / literal_eval | oracle 数据解析 | 了解风险 |
| `@staticmethod` | 配置构造辅助 | 应掌握 |
| `__all__` | requestgen API | 了解 |

## 32. 按源码文件通读

### 1. `sim/faas/core.py`

重点语法：

- 类组合。
- `Enum`。
- `NamedTuple`。
- 抽象基类。
- 魔术方法。
- `@property`。
- 静态方法。

读懂目标：

- 函数、镜像、容器、副本、请求之间的关系。
- `FaasSystem` 和 `FunctionSimulator` 定义了哪些接口。
- 请求 ID 如何由生成器产生。

### 2. `sim/core.py`

重点语法：

- 继承 `simpy.Environment`。
- 业务环境字段扩展。
- 类型标注。
- `yield env.timeout(...)`。
- Numpy 模型输入。

读懂目标：

- faas-sim 的 `Environment` 比 SimPy 环境多了哪些业务字段。
- `NodeState` 保存哪些节点运行时状态。
- timeout listener 如何终止仿真。

### 3. `sim/faas/system.py`

重点语法：

- `yield from`。
- `simpy.Store`。
- `defaultdict`。
- `Counter`。
- 生成器协程。
- 日志和指标记录。

读懂目标：

- 函数部署如何触发扩容。
- 副本如何进入调度队列。
- 请求如何等待可用副本并执行。
- 调度 worker 如何消费 `scheduler_queue`。

### 4. `sim/faassim.py`

重点语法：

- 装配对象。
- Mixin 多继承。
- 工厂模式。
- 异常边界。

读懂目标：

- Simulation 如何初始化环境。
- Benchmark 如何接入环境。
- SimulatorFactory 如何创建函数模拟器。

### 5. `sim/requestgen.py`

重点语法：

- 无限生成器。
- `next(generator)`。
- `yield env.timeout(...)`。
- `env.process(...)`。
- pickle。
- Pandas。

读懂目标：

- RPS profile 如何变成到达间隔。
- 到达间隔如何触发函数调用。
- 预录制请求如何保存和重放。

### 6. `sim/resource.py`

重点语法：

- 双下划线字段。
- `deepcopy`。
- `@dataclass`。
- `defaultdict(lambda: defaultdict(list))`。
- Numpy 平均值。
- 后台监控协程。

读懂目标：

- 资源占用如何登记、移除和汇总。
- 资源窗口如何保存。
- ResourceMonitor 如何周期采样。

### 7. `sim/metrics.py` 和 `sim/logging.py`

重点语法：

- 结构化日志。
- `NamedTuple`。
- `**tags` / `**kwargs`。
- Pandas DataFrame。
- 属性方法。

读懂目标：

- 指标如何写入 Record。
- 如何按 measurement 导出 DataFrame。
- 仿真时钟如何转成时间戳。

### 8. `sim/oracle/oracle.py`

重点语法：

- 继承。
- 统一接口。
- Pandas 读 CSV、筛选、采样。
- lambda apply。
- `literal_eval` 和 `eval`。
- 字符串解析。

读懂目标：

- 经验数据如何变成启动/执行时间估计。
- Oracle 返回的 `(metric_name, value)` 如何被上层使用。
- 拟合分布采样器如何封装。

### 9. `sim/skippy.py`、`topology.py`、`docker.py`

重点语法：

- 适配器函数。
- 外部库对象构造。
- `defaultdict`。
- 字符串解析。
- `yield flow.start()`。

读懂目标：

- faas-sim 对象如何转换给 Skippy。
- Docker 镜像如何登记和查找。
- 网络流如何转成仿真时间。

## 33. 一条请求的语法链路

下面用简化版串起 `sim` 中最核心的语法：

```python
def function_trigger(env, deployment, ia_generator):
    while True:
        ia = next(ia_generator)
        yield env.timeout(ia)
        env.process(env.faas.invoke(FunctionRequest(deployment.name)))
```

请求进入平台：

```python
def invoke(self, request):
    replicas = self.get_replicas(request.name, FunctionState.RUNNING)
    if not replicas:
        yield from self.poll_available_replica(request.name)

    replica = self.next_replica(request)
    yield from simulate_function_invocation(self.env, replica, request)
```

执行模拟器：

```python
def simulate_function_invocation(env, replica, request):
    yield from replica.simulator.invoke(env, replica, request)
```

这条链路涉及：

| 代码 | 语法 | 含义 |
| --- | --- | --- |
| `next(ia_generator)` | 生成器取值 | 取得下一次请求到达间隔 |
| `yield env.timeout(ia)` | SimPy 等待 | 仿真时间推进到下一次到达 |
| `env.process(...)` | 启动并发进程 | 每个请求独立调用 |
| `FunctionRequest(...)` | 业务对象 | 创建请求并生成 ID |
| `get_replicas(..., RUNNING)` | 枚举状态筛选 | 只使用可运行副本 |
| `yield from poll_available_replica` | 等待子流程 | scale-from-zero 等待副本 |
| `yield from simulate_function_invocation` | 生命周期串联 | 等待实际执行完成 |

## 34. 通读前检查清单

如果能回答这些问题，说明已经具备通读 `sim` 源码的语法基础：

- `FunctionDeployment.name` 为什么能直接访问函数名？
- `FunctionState.RUNNING` 比字符串 `"RUNNING"` 好在哪里？
- `FunctionRequest.id_generator = counter()` 为什么所有请求共享一个递增 ID 源？
- `yield from self.scale_up(...)` 和 `env.process(self.scale_up(...))` 有什么区别？
- `self.scheduler_queue.put((replica, services))` 里队列保存的是什么对象？
- `defaultdict(list)` 为什么可以直接 append？
- `ResourceUtilization.__resources` 为什么外部不能直接 `obj.__resources`？
- `FunctionResourceCharacterization["cpu"]` 为什么能工作？
- `SimpleFunctionSimulator` 的 `deploy()` 和 `invoke()` 分别来自哪个父类？
- `RuntimeLogger.log(..., **tags)` 中 `tags` 是什么？
- `pd.concat(dfs)` 和 `df.loc[...]` 在 Oracle 中做什么？
- `np.array(x).reshape((1, -1))` 为什么用于模型输入？
- `except simpy.Interrupt: pass` 为什么通常表示后台进程正常退出？

## 35. 建议练习

1. 手写 `Function`、`FunctionDeployment`、`FunctionReplica` 三个最小类，模拟对象组合。
2. 用 `Enum` 写一个副本状态机，筛选出 `RUNNING` 副本。
3. 写一个 `counter()` 生成器，为请求分配递增 ID。
4. 用 `yield from` 串联 `deploy -> startup -> setup` 三个子生成器。
5. 用 `simpy.Store` 写一个调度队列，生产者放入 `(replica, services)`，worker 取出处理。
6. 用 `defaultdict(list)` 维护 `function_name -> replicas`。
7. 写一个 `RuntimeLogger`，支持 `log("cpu", 0.5, node="n1")`。
8. 用 Pandas 读取一个小 DataFrame，按状态筛选 `passed` 行。
9. 用 Numpy 把资源列表转成二维模型输入。
10. 写一个 `Oracle` 基类和两个子类，统一返回 `(metric_name, value)`。

完成这些练习后，再读 `sim/faas/system.py` 和 `sim/oracle/oracle.py` 会顺畅很多。
