# 15 · converter 外部格式转换

> 本文档解析 `ether/converter/` 子包(2 个文件,共 43 行),把 Ether 拓扑转成外部工具格式。
>
> **核心内容**:`converter/pyvis.py` —— 转 PyVis 交互式 HTML 网络图

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 2 | 包入口(空 docstring) |
| `pyvis.py` | 43 | Ether 拓扑 → PyVis Network 转换 |

## 2. `converter/pyvis.py` 完整解析

### 完整代码

```python
"""PyVis 转换文件,把 Ether 拓扑中的节点、链路和连接转换为 PyVis Network,可生成交互式 HTML 网络图。"""

from pyvis.network import Network

from ether.core import Link, Node, Connection
from ether.topology import Topology


def topology_to_pyvis(topology: Topology) -> Network:
    net = Network(height='90%', width='100%', heading='Urban Sensing')
    for node in topology.nodes:
        if isinstance(node, Link):
            net.add_node(str(node), label='Link', shape='ellipse')
        elif isinstance(node, Node):
            color = {'background': '#fff'}
            if 'client' in node.name:
                color['border'] = 'green'
            elif 'broker' in node.name:
                color['border'] = 'red'
            net.add_node(str(node), label=node.name, shape='box', color=color)
        else:
            net.add_node(str(node), label=str(node), shape='box', color={'border': '#000', 'background': '#fff'})

    for edge in topology.edges:
        data = topology[edge[0]][edge[1]]
        latency = 0
        if 'connection' in data and isinstance(data['connection'], Connection):
            latency = data['connection'].get_mode_latency()
        elif 'latency' in data:
            latency = data['latency']
        if latency > 0:
            net.add_edge(str(edge[0]), str(edge[1]), label=f'{latency:.1f}', color='red')
        else:
            net.add_edge(str(edge[0]), str(edge[1]))

    return net
```

## 3. 节点分类处理

| 节点类型 | 标签 | 形状 | 颜色 |
|---|---|---|---|
| `Link` | `'Link'` | ellipse(椭圆) | 默认 |
| `Node`,name 含 `'client'` | `node.name` | box(矩形) | **绿色边框** |
| `Node`,name 含 `'broker'` | `node.name` | box | **红色边框** |
| `Node`,其他 | `node.name` | box | 默认 |
| 其他(透明链路 / internet 节点) | `str(node)` | box | 默认黑色边框 |

## 4. 边处理

```python
for edge in topology.edges:
    data = topology[edge[0]][edge[1]]
    latency = 0
    if 'connection' in data and isinstance(data['connection'], Connection):
        latency = data['connection'].get_mode_latency()  # 走 Connection 众数
    elif 'latency' in data:
        latency = data['latency']                       # 走 internet 字段
    if latency > 0:
        net.add_edge(..., label=f'{latency:.1f}', color='red')   # 红色高亮
    else:
        net.add_edge(...)
```

**latency 提取双源**(同 `topology.py` 的 `_update_rtt`):

- ether 自己的边 → `Connection.get_mode_latency()`(稳定众数)
- 互联网图边 → `data['latency']` 字段

**有 latency 的边用红色 + 标签**(如 `227.4`),没 latency 的边普通显示。

## 5. 典型用法

```python
from ether.topology import Topology
from ether.scenarios.urbansensing import UrbanSensingScenario
from ether.converter.pyvis import topology_to_pyvis

t = Topology()
t.add(UrbanSensingScenario(num_cells=3))
t.load_inet_graph('cloudping')

net = topology_to_pyvis(t)
net.show('topology.html')              # 生成可交互的 HTML
# 或者 net.save_graph('topology.html')
```

生成的 `topology.html`:

- 可在浏览器中打开
- 鼠标拖拽节点
- 鼠标悬停查看标签
- 边有 latency 标签(红色)
- 节点有 name 标签

## 6. PyVis vs NetworkX 可视化对比

| 维度 | `vis.draw_basic`(NetworkX) | `converter.pyvis.topology_to_pyvis`(PyVis) |
|---|---|---|
| 输出 | matplotlib 静态图 | HTML 交互式 |
| 交互 | 无 | 拖拽、缩放、悬停 |
| 大拓扑 | 拥挤看不清 | 力导向布局 + 缩放 |
| 论文插图 | ✅ 适合(高 dpi) | 一般不直接用 |
| 补充材料 | 一般 | ✅ 适合(可点击) |
| 调试 | ✅ 快速 | 慢(要开浏览器) |

## 7. 对论文的用处

| 论文场景 | 价值 |
|---|---|
| **论文插图** | `vis.draw_basic` 出高 dpi 静态图(主图) |
| **补充材料** | `topology_to_pyvis` 出 HTML(读者可点开看) |
| **演示视频** | HTML 交互图录屏 |
| **答辩 PPT** | HTML 演示给评委看拓扑结构 |
| **延迟高亮** | 红色边 + 标签,直观展示"哪里慢" |

### 推荐工作流

```python
# 1. 出 publication-quality 图(主图)
import matplotlib.pyplot as plt
from ether.vis import draw_basic
fig, ax = plt.subplots(figsize=(12, 8))
draw_basic(topology)
plt.savefig('paper_fig_3_topology.pdf', bbox_inches='tight', dpi=300)

# 2. 出 supplementary HTML(可交互)
from ether.converter.pyvis import topology_to_pyvis
net = topology_to_pyvis(topology)
net.save_graph('supplementary_topology.html')
```
