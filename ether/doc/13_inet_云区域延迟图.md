# 13 · inet 云区域延迟图

> 本文档解析 `ether/inet/` 子包(6 个文件 + 6 个 graphml 数据),提供真实云区域间延迟数据。
>
> **核心内容**:graphml 加载/保存(`graph.py`)+ 3 个数据源抓取(`fetch/`)+ 6 个真实数据文件

## 1. 子包概览

| 文件 | 行数 | 角色 |
|---|---|---|
| `__init__.py` | 3 | 包入口 |
| `graph.py` | 105 | GraphML 加载/保存/写入图 |
| `fetch/__init__.py` | 18 | 数据源注册(sources 字典) |
| `fetch/data.py` | 15 | Measurement 数据类 |
| `fetch/cloudping.py` | 44 | AWS 区域延迟抓取 |
| `fetch/gcloudping.py` | ~35 | GCP 区域延迟抓取 |
| `fetch/wondernetwork.py` | ~48 | WonderNetwork 数据抓取 |

**数据文件**(`inet/graphs/`):

- `cloudping_2020_05_18.graphml`(20KB)
- `cloudping_2020_06_20.graphml`(39KB)
- `cloudping_latest.graphml`(39KB,与 06_20 相同)
- `gcloudping_2020_05_18.graphml`(21KB)
- `gcloudping_latest.graphml`(21KB)
- `wondernetwork_2020_05_18.graphml`(36KB)
- `wondernetwork_2020_06_20.graphml`(71KB)
- `wondernetwork_latest.graphml`(71KB)

## 2. `graph.py` —— GraphML 加载/保存

### 全局

```python
graph_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), 'graphs'))
```

`graph_directory` 指向 `inet/graphs/` 子目录。

### 6 个函数

| 函数 | 行为 |
|---|---|
| `load_latest(graph, source) → nx.DiGraph` | `load_tagged(graph, source, 'latest')` |
| `load_tagged(graph, source, tag) → nx.DiGraph` | 加载 `<source>_<tag>.graphml` |
| `load_from_file(graph, file_path, node_prefix='internet_')` | 读 graphml → 加前缀 → 写进 graph |
| `fetch_to_graph(graph, module)` | 在线抓数据(走 `module.fetch()`) |
| `add_to_graph(graph, measurements, node_prefix='')` | 把 measurements 写进 graph |
| `save_graph(g, path) → None` | `nx.write_graphml(g, path=path)` |
| `load_graph(path) → nx.Graph` | `nx.read_graphml(path)` |

### `load_from_file` 关键代码

```python
def load_from_file(graph, file_path, node_prefix='internet_'):
    inet_graph = load_graph(file_path)   # 读 graphml

    for src, dst, data in inet_graph.edges.data():
        graph.add_edge(node_prefix + src, node_prefix + dst, **data)
```

**关键设计:节点前缀 `internet_`**

避免和 topology 内部其他顶点冲突:

- 用户节点:`cloudvm_0`、`rpi3_0` 等
- 透明交换机:`switch_lan_0`
- 互联网节点:`internet_us-east-1`、`internet_ap-southeast-1`

### `add_to_graph` 关键代码

```python
def add_to_graph(graph, measurements, node_prefix=''):
    for m in measurements:
        if m.source == m.destination:   # 自环跳过
            continue

        src = f'{node_prefix}{m.source}'
        dst = f'{node_prefix}{m.destination}'

        graph.add_edge(src, dst, latency=m.avg)
```

把 measurements 列表(在线抓的数据)转成图边。

### 与 `topology.py` 的配合

`topology.py` 的 `_update_rtt` 双源支持:

```python
if 'connection' in edge_data and isinstance(edge_data['connection'], Connection):
    latency += connection.get_mode_latency() if use_mode else connection.get_latency()
elif 'latency' in edge_data:
    # ← 互联网 graphml 走这条分支
    latency += edge_data['latency']
```

## 3. `fetch/` —— 数据抓取

### `data.py`:Measurement 数据类

```python
class Measurement(NamedTuple):
    source: str
    destination: str
    avg: float
    max: float = -1
    min: float = -1
```

统一表示"两个区域间的延迟测量":平均值 + 最大/最小(部分数据源提供)。

### `__init__.py`:数据源注册

```python
from ether.inet.fetch import cloudping, gcloudping, wondernetwork
from ether.inet.fetch.data import Measurement

name = 'fetch'
sources = {
    'cloudping': cloudping,
    'gcloudping': gcloudping,
    'wondernetwork': wondernetwork
}
```

`sources` 是 CLI 用的数据源映射。

### `cloudping.py` (AWS 区域)

```python
resource = 'https://api.cloudping.co/averages/day'

def fetch() -> List[Measurement]:
    data = _get_averages()
    result = list()
    for region_from in data:
        src = region_from['region']
        for region_to in region_from['averages']:
            dst = region_to['regionTo']
            avg = region_to['average']
            result.append(Measurement(src, dst, avg))
    return result

def _get_averages(days: int = 7):
    url = f'{resource}/{days}'
    response = requests.get(url)
    if response.status_code != 200:
        raise RuntimeError(f'invalid response with code {response.status_code}')
    return response.json()
```

抓过去 7 天平均延迟。

### `gcloudping.py` / `wondernetwork.py`

类似结构,各自从 GCP 接口 / WonderNetwork 抓数据,统一转 `Measurement`。

## 4. GraphML 数据长什么样

`cloudping_latest.graphml` 片段:

```xml
<?xml version='1.0' encoding='utf-8'?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns/...">
  <key attr.name="latency" attr.type="double" for="edge" id="d0" />
  <graph edgedefault="directed">
    <node id="af-south-1" />
    <node id="eu-north-1" />
    <node id="ap-south-1" />
    ...
    <edge source="af-south-1" target="eu-north-1">
      <data key="d0">227.43</data>
    </edge>
    <edge source="af-south-1" target="ap-south-1">
      <data key="d0">371.82</data>
    </edge>
    ...
  </graph>
</graphml>
```

- **节点**:AWS/GCP 区域 ID(如 `us-east-1`, `ap-southeast-1`)
- **边属性**:`latency`(毫秒,如 af-south-1 → eu-north-1 = 227.43ms)
- 1165 行数据,20+ AWS 区域完全图

## 5. 典型用法

```python
from ether.topology import Topology
from ether.scenarios.cloudregions import CloudRegionsScenario

# 1. 建拓扑 + 加场景
t = Topology()
t.add(CloudRegionsScenario(
    regions=['us-east-1', 'eu-west-1', 'ap-southeast-1'],
    region_size=[(5, 2), (5, 2), (5, 2)]
))

# 2. 加载真实云区域延迟
t.load_inet_graph('cloudping')

# 3. 查询跨区域 RTT
# 找 'internet_us-east-1' 节点
us_node = [n for n in t.nodes if n == 'internet_us-east-1'][0]
eu_node = [n for n in t.nodes if n == 'internet_eu-west-1'][0]
rtt = t.route(us_node, eu_node).rtt
print(f'us-east-1 → eu-west-1 RTT: {rtt:.2f}ms')  # ~80ms(实测)
```

## 6. 怎么更新 graphml 数据

### 选项 1:用 ether 自带 CLI(见 14_cli_命令行工具.md)

```bash
python -m ether.cli.inet
```

并发抓 3 个数据源,保存为 `<source>_<YYYY_MM_DD>.graphml` 和 `<source>_latest.graphml`。

### 选项 2:用 Python API

```python
import networkx as nx
from ether.inet.graph import add_to_graph, save_graph
from ether.inet.fetch import sources

graph = nx.DiGraph()
for name, source in sources.items():
    add_to_graph(graph, source.fetch())
    save_graph(graph, f'graphs/{name}_latest.graphml')
```

## 7. 对论文的用处

| 论文实验要素 | inet 提供的接口 |
|---|---|
| **真实云区域延迟** | `Topology.load_inet_graph('cloudping')` |
| **AWS 区域** | `cloudping_latest.graphml`(20+ AWS 区域) |
| **GCP 区域** | `gcloudping_latest.graphml` |
| **多云混合** | `wondernetwork_latest.graphml` |
| **更新数据** | `python -m ether.cli.inet` |
| **自定义测量数据** | `add_to_graph(graph, my_measurements)` |

### 论文实验设置

```python
# 模拟"全球云调度"实验
t = Topology()
t.add(UrbanSensingScenario(num_cells=5))         # 5 个城区
t.load_inet_graph('cloudping')                   # AWS 区域延迟

# 跨区域函数调用(从城区到云)
rtt = t.route(city_node, cloudvm_us_node).rtt    # 真实跨大洲延迟
```
