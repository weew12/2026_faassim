# 07 · 对象存储索引 (`core/storage.py`)

> 解析文件：`skippy/core/storage.py`（113 行）
>
> 本文件提供一个**轻量级内存索引**，用来描述对象数据位于哪些存储节点上。它服务于**数据本地性调度**：当函数 Pod 标签声明需要从某个对象路径读取数据，或向某个对象路径写回数据时，`DataLocalityPriority` 会查询 `StorageIndex`，估算候选执行节点与存储节点之间的数据传输时间。

## 1. 类与字段概览

```text
DataItem (NamedTuple)
├── bucket: str
├── name:   str
└── size:   int         # 字节

StorageIndex
├── buckets: Dict[str, Set[str]]                  # bucket -> 节点集合
├── tree:    Dict[Tuple[str, str], Set[str]]      # (bucket, object) -> 节点集合
└── items:   Dict[Tuple[str, str], DataItem]      # (bucket, object) -> DataItem
```

## 2. `DataItem` — 对象存储中的数据项

```python
class DataItem(NamedTuple):
    bucket: str
    name:   str
    size:   int
```

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `bucket` | `str` | 对象桶名称。 |
| `name` | `str` | 桶内对象名称。 |
| `size` | `int` | 对象大小，单位字节。 |

> 用 `NamedTuple` 而非普通类：调度器只需读取三个字段，`NamedTuple` 提供不可变 + 字段访问，比 dataclass 轻量。

## 3. `StorageIndex` — 对象存储位置索引

### 3.1 业务作用

模拟 S3 / MinIO 一类对象存储在边缘集群中的**数据位置**。它**不执行真实 I/O**，只记录：

- bucket 部署在哪些节点；
- 对象元数据是什么；
- 对象副本位于哪些节点。

调度器据此判断「函数靠近哪个节点执行可以减少网络传输代价」。

### 3.2 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `buckets` | `Dict[str, Set[str]]` | `bucket` → 存放该 bucket 的节点集合。一个 bucket 可以映射到多个节点以表达副本。 |
| `tree` | `Dict[Tuple[str, str], Set[str]]` | `(bucket, object)` → 存放该对象的节点集合。 |
| `items` | `Dict[Tuple[str, str], DataItem]` | `(bucket, object)` → 对象元数据。 |

### 3.3 关键代码

```python
def __init__(self) -> None:
    super().__init__()
    self.buckets = defaultdict(set)
    self.tree    = defaultdict(set)
    self.items   = dict()
```

- `defaultdict(set)`：bucket / 对象不存在时自动返回空集合，简化「是否登记过」的判断；
- `items` 用普通 `dict`：DataItem 的 KeyError 应当被 `stat` 显式处理，不该自动创建空数据。

## 4. API 方法

### 4.1 `mb(name, node)` — 在指定节点上创建 bucket

```python
def mb(self, name: str, node: str):
    self.buckets[name].add(node)
```

| 参数 | 含义 |
| --- | --- |
| `name` | bucket 名称。 |
| `node` | 承载该 bucket 的存储节点名称。 |

> 命名沿用类 Unix 命令 `mkdir`。本方法只维护索引关系，不创建真实存储目录。

### 4.2 `put(data)` — 登记对象数据项

```python
def put(self, data: DataItem):
    nodes = self.get_bucket_nodes(data.bucket)
    if not nodes:
        raise KeyError('no nodes that host bucket %s' % data.bucket)

    k = (data.bucket, data.name)
    self.items[k] = data
    # 当前实现将对象视为存在于该 bucket 的所有节点上
    for node in nodes:
        self.tree[k].add(node)
```

| 步骤 | 说明 |
| --- | --- |
| 1 | 查 `data.bucket` 的承载节点集合。 |
| 2 | 若该 bucket 没有承载节点，**直接抛 `KeyError`**——调度器无法定位对象。 |
| 3 | 写入对象元数据到 `items`。 |
| 4 | 把对象登记到该 bucket 的**所有**承载节点上（以 set 形式去重）。 |

### 4.3 `stat(bucket, name) -> DataItem | None`

```python
def stat(self, bucket: str, name: str) -> DataItem:
    k = (bucket, name)
    return self.items.get(k)
```

查询对象元数据；对象不存在时返回 `None`。

### 4.4 `get_bucket_nodes(bucket) -> Set[str]`

```python
def get_bucket_nodes(self, bucket: str) -> Set[str]:
    return self.buckets[bucket]
```

返回承载指定 bucket 的节点集合。

> 因 `self.buckets` 是 `defaultdict(set)`，未注册的 bucket 会返回空集合——调用方应自行处理。

### 4.5 `get_data_nodes(bucket, name) -> Set[str] | None`

```python
def get_data_nodes(self, bucket: str, name: str) -> Set[str]:
    k = (bucket, name)
    return self.tree.get(k)
```

返回保存指定对象的节点集合；对象未登记时返回 `None`（因为底层是普通 dict 而非 defaultdict）。

### 4.6 `print_ls_tree()` — 调试打印

```python
def print_ls_tree(self):
    tree = defaultdict(lambda: defaultdict(list))
    for (bucket, item), nodes in self.tree.items():
        for node in nodes:
            tree[node][bucket].append(item)

    for node, buckets in tree.items():
        print(f'/{node}')
        for bucket, items in buckets.items():
            print(f'/{node}/{bucket}')
            for item in items:
                print(f'/{node}/{bucket}/{item}')
```

- 仅用于调试和人工检查，**不参与调度决策**；
- 以类似 `find` 的路径树形式打印对象位置索引。

## 5. 与 `DataLocalityPriority` 的衔接

```text
Pod 标签
   data.skippy.io/receives-from-storage/path = <bucket>/<object>
            │
            ▼
DataLocalityPriority.calculate_recv_time
   ├─ path.split('/') → (bucket, object)
   ├─ context.storage_index.stat(bucket, object)        # 取 DataItem.size
   ├─ context.get_storage_nodes(path)
   │     └─ ClusterContext.get_storage_nodes
   │           └─ StorageIndex.get_bucket_nodes(bucket) # 取存储节点集合
   └─ 遍历存储节点 → 选最差带宽链路 → time = size / bandwidth
```

## 6. 跨模块依赖

| 引用来源 | 使用的成员 |
| --- | --- |
| `clustercontext.py` | `get_bucket_nodes`（通过 `storage_index.get_bucket_nodes` 间接调用） |
| `priorities.py` (`DataLocalityPriority`) | `storage_index.stat`, `storage_index.get_bucket_nodes`（通过 `context.storage_index`） |

## 7. 一个最小使用示例

```python
idx = StorageIndex()
idx.mb('images', 'node-a')              # bucket 'images' 由 node-a 承载
idx.mb('images', 'node-b')              # bucket 同时承载在 node-b
idx.put(DataItem(bucket='images', name='cat.jpg', size=10 * 1024 * 1024))

idx.get_bucket_nodes('images')           # {'node-a', 'node-b'}
idx.stat('images', 'cat.jpg')            # DataItem(bucket='images', name='cat.jpg', size=10485760)
idx.get_data_nodes('images', 'cat.jpg')  # {'node-a', 'node-b'}
```
