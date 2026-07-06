# 06 · util / export / vis 工具与导出

> 本文档解析 `ether/` 一级目录的三个工具类文件:`util.py`(57 行)、`export.py`(47 行)、`vis.py`(49 行)。
>
> **核心内容**:容量字符串解析、TAM 格式 JSON 导出、NetworkX 拓扑可视化

## 1. 文件清单

| 文件 | 行数 | 角色 |
|---|---|---|
| `util.py` | 57 | 容量字符串解析(Kubernetes / Docker 资源格式 ↔ 字节数) |
| `export.py` | 47 | 拓扑导出 TAM 格式 JSON |
| `vis.py` | 49 | NetworkX 拓扑可视化(4 类节点分色) |

## 2. `util.py` —— 容量字符串解析

### 全局表

```python
__size_conversions = {
    'K':  10**3,  'Ki': 2**10,
    'M':  10**6,  'Mi': 2**20,
    'G':  10**9,  'Gi': 2**30,
    'T':  10**12, 'Ti': 2**40,
    'P':  10**15, 'Pi': 2**50,
    'E':  10**18, 'Ei': 2**60,
}
__size_pattern = re.compile(r"([0-9]+)([a-zA-Z]*)")
```

| 单位 | SI(10^x) | 二进制(2^x) |
|---|---|---|
| K / Ki | 10³ | 2¹⁰ |
| M / Mi | 10⁶ | 2²⁰ |
| G / Gi | 10⁹ | 2³⁰ |
| T / Ti | 10¹² | 2⁴⁰ |
| P / Pi | 10¹⁵ | 2⁵⁰ |
| E / Ei | 10¹⁸ | 2⁶⁰ |

**SI(无 i)**:十进制倍数(磁盘厂商常用)
**二进制(带 i)**:真正的 2^x 字节(Kubernetes、Docker 用这种)

### `parse_size_string(size_string) -> int`

```python
def parse_size_string(size_string: str) -> int:
    m = __size_pattern.match(size_string)
    if len(m.groups()) > 1:
        number = m.group(1)
        unit = m.group(2)
        return int(number) * __size_conversions.get(unit, 1)
    else:
        return int(m.group(1))
```

| 输入 | 输出 |
|---|---|
| `"1G"` | 1,000,000,000(SI 十进制) |
| `"1Gi"` | 1,073,741,824(2^30) |
| `"512Mi"` | 536,870,912(512 * 2^20) |
| `"999036Ki"` | 1,022,852,864(999036 * 2^10) |
| `"1024"` | 1024(无单位,默认 1) |

### `to_size_string(num_bytes, unit='M', precision=1) -> str`

```python
def to_size_string(num_bytes, unit='M', precision=1):
    factor = __size_conversions[unit]
    value = num_bytes / factor
    fmt = f'%0.{precision}f{unit}'
    return fmt % value
```

格式化回带单位的字符串,用于日志/展示。

### 在 ether 中怎么用

`blocks/nodes.py` 的 `create_node(mem='1G')` 就是调 `parse_size_string`:

```python
def create_node(name, cpus, mem, arch, labels) -> Node:
    capacity = Capacity(cpu_millis=cpus * 1000, memory=parse_size_string(mem))
    return Node(name, capacity=capacity, arch=arch, labels=labels)
```

直接对接 Kubernetes / Docker 资源字符串。

### 对论文的用处

- 节点内存建模直接用 Kubernetes 风格字符串(`mem='1Gi'`)
- 论文实验配置可以更贴近真实 K8s 资源定义

## 3. `export.py` —— TAM 格式 JSON 导出

### `export_to_tam_json(topology, output_file, value_projector)`

```python
def export_to_tam_json(topology, output_file, value_projector):
    nodes = []
    links = []
    if value_projector is None:
        value_projector = lambda: 0

    # 1. 遍历所有节点
    for node in topology.nodes:
        if isinstance(node, str):
            nodes.append({
                'id': id(node),
                'name': node,
                'value': 0
            })
            continue
        nodes.append({
            'id': id(node),
            'name': node.name if isinstance(node, Node) else node.tags['name'],
            'value': value_projector(node)
        })

    # 2. 遍历所有边
    for edge in topology.edges.values():
        links.append({
            'source': id(edge['connection'].source),
            'target': id(edge['connection'].target),
            'directed': edge['directed']
        })

    # 3. 写 JSON
    full = {'nodes': nodes, 'links': links}
    with open(output_file, 'w') as file:
        json.dump(full, file)
        file.flush()
        file.close()
```

### 节点分类处理

| 节点类型 | name 字段 | value 字段 |
|---|---|---|
| 字符串(透明链路 / internet 节点) | 字符串本身 | 0 |
| Node 实例 | `node.name` | `value_projector(node)` |
| Link 实例 | `link.tags['name']` | `value_projector(node)` |

`value_projector` 是用户传入的回调,把节点映射成数值(比如节点 CPU 利用率、内存使用、任务数等),用于外部工具按值大小着色。

### 边处理

每条边导出:

- `source`: `id(connection.source)`(Python 内存地址,作为唯一标识)
- `target`: `id(connection.target)`
- `directed`: 是否是有向边

### 输出格式

```json
{
  "nodes": [
    {"id": 140234567890, "name": "cloudvm_0", "value": 80},
    {"id": 140234567891, "name": "switch_lan_0", "value": 0},
    ...
  ],
  "links": [
    {"source": 140234567890, "target": 140234567891, "directed": false},
    ...
  ]
}
```

### 用途

**TAM(Topology Analysis Module)类工具的 JSON 输入** —— 适合外部可视化或持久化。

## 4. `vis.py` —— NetworkX 拓扑可视化

### `draw_basic(topology)`

```python
def draw_basic(topology):
    pos = nx.kamada_kawai_layout(topology)  # positions for all nodes

    hosts = [node for node in topology.nodes if isinstance(node, Node)]
    links = [node for node in topology.nodes if isinstance(node, Link)]
    switches = [node for node in topology.nodes if str(node).startswith('switch_')]

    nx.draw_networkx_nodes(topology, pos, nodelist=hosts, node_color='b', node_size=300, alpha=0.8)
    nx.draw_networkx_nodes(topology, pos, nodelist=links, node_color='g', node_size=50, alpha=0.9)
    nx.draw_networkx_nodes(topology, pos, nodelist=switches, node_color='y', node_size=200, alpha=0.8)
    nx.draw_networkx_nodes(topology, pos,
                           nodelist=[n for n in topology.nodes if isinstance(n, str) and n.startswith('internet')],
                           node_color='r', node_size=800, alpha=0.8)

    nx.draw_networkx_edges(topology, pos, width=1.0, alpha=0.5)
    nx.draw_networkx_labels(topology, pos, dict(zip(hosts, hosts)), font_size=10)
    nx.draw_networkx_labels(topology, pos, dict(zip(links, [l.tags['type'] for l in links])), font_size=8)
```

### 4 类节点分色

| 节点类型 | 颜色 | size | 含义 |
|---|---|---|---|
| `Node` 实例 | 🔵 蓝 (b) | 300 | 计算节点(主机) |
| `Link` 实例 | 🟢 绿 (g) | 50 | 链路 |
| 以 `switch_` 开头的字符串 | 🟡 黄 (y) | 200 | 透明交换机 |
| 以 `internet` 开头的字符串 | 🔴 红 (r) | 800 | 互联网区域节点 |

### 布局

`kamada_kawai_layout` —— 基于弹簧模型的力导向布局,适合展示网络拓扑结构。

### 标签

- 主机:`host.name`
- 链路:`link.tags['type']`(如 `node`、`shared`、`uplink`、`downlink`)

### 用法

```python
import matplotlib.pyplot as plt
from ether.vis import draw_basic

fig, ax = plt.subplots(figsize=(12, 8))
draw_basic(topology)
plt.title('Ether Topology')
plt.axis('off')
plt.show()
```

### 备注

- 适合"快速预览"和"开发期调试"
- **论文 publication-quality 图建议**用 `converter/pyvis.py`(交互式 HTML) 或 `scientific-visualization` skill
- `vis.py` 是基础版,如果需要更精细的控制(节点大小映射数值、边颜色映射时延等)需要自己扩展

## 5. 对论文的接口清单

| 论文实验要素 | 这三个文件提供的接口 | 关键位置 |
|---|---|---|
| 节点内存配置(K8s 风格) | `util.parse_size_string("1Gi")` | `util.py` 25-37 |
| 内存格式化为可读 | `util.to_size_string(num_bytes, unit='G')` | `util.py` 40-56 |
| 拓扑导出 JSON(TAM 格式) | `export.export_to_tam_json(topology, file, value_projector)` | `export.py` 9-46 |
| 拓扑快速预览图 | `vis.draw_basic(topology)` | `vis.py` 8-49 |
| 按数值映射节点属性(外部工具) | `value_projector: Callable[[Node], int]` | `export.py` 9 |

### 典型用法

```python
from ether.util import parse_size_string, to_size_string
from ether.export import export_to_tam_json
from ether.vis import draw_basic

# 容量解析
mem_bytes = parse_size_string("8Gi")              # 8,589,934,592
print(to_size_string(mem_bytes, unit='G'))        # "8.6G"

# 拓扑导出(按节点 CPU 利用率着色)
def cpu_value(node):
    return node.capacity.cpu_millis if hasattr(node, 'capacity') else 0

export_to_tam_json(topology, 'topology.json', cpu_value)

# 拓扑预览
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 8))
draw_basic(topology)
plt.show()
```
