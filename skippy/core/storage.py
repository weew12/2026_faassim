"""Skippy 对象存储索引模型。

本文件提供一个轻量级内存索引，用来描述对象数据位于哪些存储节点上。它服务于
数据本地性调度：当函数 Pod 标签声明需要从某个对象路径读取数据，或向某个对象路径
写回数据时，DataLocalityPriority 会查询 StorageIndex，估算候选执行节点与存储节点
之间的数据传输时间。
"""

from collections import defaultdict
from typing import Dict, Set, NamedTuple, Tuple


class DataItem(NamedTuple):
    """    对象存储中的数据项。

    字段：
    - ``bucket``：对象桶名称；
    - ``name``：桶内对象名称；
    - ``size``：对象大小，单位为字节。
    """

    bucket: str
    name: str
    size: int


class StorageIndex:
    """    对象存储位置索引。

    业务作用：
    该类模拟 S3/MinIO 一类对象存储在边缘集群中的数据位置。它不执行真实 I/O，只记录
    bucket 部署在哪些节点、对象元数据是什么、对象副本位于哪些节点。调度器据此判断
    函数靠近哪个节点执行可以减少网络传输代价。
    """

    # bucket -> 存放该 bucket 的节点集合。
    buckets: Dict[str, Set[str]]
    # (bucket, object) -> 存放该对象的节点集合。
    tree: Dict[Tuple[str, str], Set[str]]
    # (bucket, object) -> 对象元数据。
    items: Dict[Tuple[str, str], DataItem]

    def __init__(self) -> None:
        """初始化空的对象存储索引。"""
        super().__init__()
        # 记录每个 bucket 所在节点；一个 bucket 可以映射到多个节点以表达副本。
        self.buckets = defaultdict(set)
        # 记录每个对象实际可从哪些节点读取。
        self.tree = defaultdict(set)
        # 记录对象的 bucket/name/size 元数据。
        self.items = dict()

    def mb(self, name: str, node: str):
        """        在指定节点上创建 bucket。

        参数：
        - ``name``：bucket 名称；
        - ``node``：承载该 bucket 的存储节点名称。
        """
        # 只维护索引关系，不创建真实存储目录。
        self.buckets[name].add(node)

    def put(self, data: DataItem):
        """        登记对象数据项。

        该方法会检查对象所属 bucket 是否已有承载节点；若没有承载节点，则说明调度器
        无法定位对象，直接抛出异常。登记成功后，对象会出现在该 bucket 的所有承载节点上。
        """
        nodes = self.get_bucket_nodes(data.bucket)
        if not nodes:
            raise KeyError('no nodes that host bucket %s' % data.bucket)

        # 对象索引键由 bucket 和对象名共同组成。
        k = (data.bucket, data.name)
        # 保存对象元数据，供后续 stat 和数据本地性评分读取对象大小。
        self.items[k] = data

        # 当前实现将对象视为存在于该 bucket 的所有节点上。
        for node in nodes:
            self.tree[k].add(node)

    def stat(self, bucket: str, name: str) -> DataItem:
        """查询对象元数据；对象不存在时返回 ``None``。"""
        k = (bucket, name)
        return self.items.get(k)

    def get_bucket_nodes(self, bucket: str) -> Set[str]:
        """返回承载指定 bucket 的节点集合。"""
        return self.buckets[bucket]

    def get_data_nodes(self, bucket: str, name: str) -> Set[str]:
        """返回保存指定对象的节点集合；对象未登记时返回 ``None``。"""
        k = (bucket, name)
        return self.tree.get(k)

    def print_ls_tree(self):
        """        以类似 ``find`` 的路径树形式打印对象位置索引。

        该函数仅用于调试和人工检查，不参与调度决策。
        """
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
