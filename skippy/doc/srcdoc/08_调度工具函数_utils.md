# 08 · 调度工具函数 (`core/utils.py`)

> 解析文件：`skippy/core/utils.py`（111 行）
>
> 本文件提供调度器多个模块都会复用的基础工具：
>
> 1. **镜像名规范化**：将未带 tag 的镜像补齐为 `:latest`，与 Kubernetes / CRI 的镜像本地性判断方式保持一致；
> 2. **容量字符串解析**：把 `103M`、`512Mi` 这类实验标签中的容量值转换为字节数；
> 3. **简单计时器和递增计数器**：用于调试或生成序号。

## 1. 模块成员一览

```text
utils
├── default_image_tag: str = "latest"
├── normalize_image_name(image_name) -> str
├── parse_size_string(size_string) -> int
├── __size_conversions: Dict[str, int]     # 私有
├── __size_pattern: re.Pattern            # 私有
├── Timer
│   ├── then: float
│   ├── start() -> self
│   └── ms() -> float
└── counter(start=1) -> Iterator[int]
```

## 2. 镜像名规范化

### 2.1 常量

```python
default_image_tag: str = "latest"
```

默认镜像标签。镜像名没有显式 tag 时，调度器按 `:latest` 处理。

### 2.2 `normalize_image_name(image_name)`

```python
def normalize_image_name(image_name: str):
    # 只有当最后一个冒号出现在最后一个斜杠之前时，才说明镜像名没有 tag
    if image_name.rfind(":") <= image_name.rfind("/"):
        image_name = image_name + ":" + default_image_tag
    return image_name
```

### 2.3 业务作用

Skippy 使用镜像名作为 `images_on_nodes` 的键。如果同一个镜像有时写成 `foo`，有时写成 `foo:latest`，会导致**镜像本地性判断错误**（同一个镜像在键空间里被拆成两条记录）。因此调度前统一补齐默认 tag。

### 2.4 关键判断

`rfind(":") <= rfind("/")` 的语义：

- 若镜像名**没有冒号**（无 tag），`rfind(":")` 返回 `-1`，比 `rfind("/")` 小，条件成立 → 加 `:latest`。
- 若镜像名**有冒号在 tag 位置**（如 `foo:v1`），冒号出现在最后一个斜杠**之后**，条件不成立 → 不动。
- 若镜像名是**带端口的 registry**（如 `registry:5000/foo`），冒号出现在最后一个斜杠**之前**，条件成立 → 会把 `registry:5000/foo` 错误地变成 `registry:5000/foo:latest`。

> **已知边界**：上述 registry:port 场景不会被正确解析，但 faas-sim 实验不涉及私有 registry，因此未做特殊处理。如未来要支持，可改为正则 `^(?:[^:/]+:/)?[^:]+$`。

## 3. 容量字符串解析

### 3.1 容量单位表

```python
__size_conversions = {
    'K':  10 ** 3,   'M':  10 ** 6,   'G':  10 ** 9,
    'T':  10 ** 12,  'P':  10 ** 15,  'E':  10 ** 18,
    'Ki': 2 ** 10,   'Mi': 2 ** 20,   'Gi': 2 ** 30,
    'Ti': 2 ** 40,   'Pi': 2 ** 50,   'Ei': 2 ** 60,
}
```

支持两套单位：

- **十进制**（K / M / G / ...）：与 Kubernetes Resource Notation 中的 decimal 后缀对齐。
- **二进制**（Ki / Mi / Gi / ...）：与 Kubernetes Resource Notation 中的 binary 后缀对齐。

### 3.2 容量字符串正则

```python
__size_pattern = re.compile(r"([0-9]+)([a-zA-Z]*)")
```

匹配「整数 + 可选单位」，例如 `10M`、`512Mi`、`1000`。

### 3.3 `parse_size_string(size_string)`

```python
def parse_size_string(size_string: str) -> int:
    m = __size_pattern.match(size_string)
    if not m:
        raise ValueError('invalid size string: %s' % size_string)

    if len(m.groups()) > 1:
        number = m.group(1)
        unit   = m.group(2)
        return int(number) * __size_conversions.get(unit, 1)
    else:
        return int(m.group(1))
```

### 3.4 业务作用

faas-sim 的函数标签中会使用：

```text
data.skippy.io/receives-from-storage = 103M
```

这类字符串描述数据输入/输出大小。调度器和 Oracle 需要将其转换为**字节数**后才能估算带宽占用和传输时间。

### 3.5 行为示例

| 输入 | 输出 | 说明 |
| --- | --- | --- |
| `"103M"` | `103_000_000` | 十进制 MB。 |
| `"512Mi"` | `536_870_912` | 二进制 MiB。 |
| `"4096"` | `4096` | 无单位 → 视为字节数。 |
| `"abc"` | 抛 `ValueError` | 非法字符串。 |

> 未知单位按 `1` 处理（即 `__size_conversions.get(unit, 1)`）—— `get` 的默认值是 1。这避免了「带奇怪后缀的字符串崩溃」。

## 4. `Timer` — 简单墙上时钟计时器

```python
class Timer:
    def __init__(self) -> None:
        super().__init__()
        self.then = -1   # -1 表示尚未开始

    def start(self):
        self.then = time.time()
        return self      # 支持链式调用

    def ms(self):
        return (time.time() - self.then) * 1000
```

### 4.1 业务作用

简单墙上时钟计时器，用于**调试代码片段耗时**。

### 4.2 用法示例

```python
t = Timer().start()
do_expensive_work()
print(f'elapsed: {t.ms():.2f} ms')
```

### 4.3 注意

- 多次调用 `start` 会**重置**基准时间；
- 调用 `ms` 之前必须先 `start`，否则 `self.then = -1` 会导致返回巨大的负值。
- 暂不支持「暂停 / 恢复 / 累计」——只是最简单的瞬时计时。

## 5. `counter(start=1)` — 无限递增整数序列

```python
def counter(start: int = 1):
    n = start
    while True:
        yield n
        n += 1
```

### 5.1 业务作用

生成从 `start` 开始的无限递增整数序列。可用于给仿真对象、Pod 或临时事件生成**稳定递增编号**。

### 5.2 用法示例

```python
g = counter(1)
next(g)  # 1
next(g)  # 2
next(g)  # 3

c2 = counter(100)
next(c2)  # 100
```

### 5.3 设计要点

- 用 generator 而非 list：避免一次性分配内存，按需生成；
- 不接受 `step` 参数：实现足够轻量，需要步长可在外层 `next()` 后手动加；
- 没有终止条件：调用方自行决定何时停止（通常用 `itertools.islice`）。

## 6. 跨模块依赖

| 调用方 | 使用的成员 |
| --- | --- |
| `clustercontext.py` | `normalize_image_name` |
| `scheduler.py` | `normalize_image_name` |
| `priorities.py` | `normalize_image_name` |

`parse_size_string` / `Timer` / `counter` 是**通用工具**，目前未在 `core/` 其他文件直接调用，但保留作为基础设施供扩展使用。
