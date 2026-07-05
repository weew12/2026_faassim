"""
文件作用：data_locality 样例的数据对象与 StorageIndex 构造。

faas-sim / Skippy 使用 StorageIndex 描述对象数据在哪些存储节点上。
函数通过 Pod 标签声明需要读取哪个对象，调度器据此估算候选节点到数据所在节点的传输代价。
"""

from dataclasses import dataclass

from skippy.core.storage import StorageIndex, DataItem
from skippy.core.utils import parse_size_string


@dataclass
class DataLocalityObject:
    """
    样例数据对象描述。
    """

    bucket: str
    name: str
    size: str
    storage_node: str

    @property
    def path(self) -> str:
        """
        返回 faas-sim 标签使用的 bucket/object 路径。
        """
        return f"{self.bucket}/{self.name}"

    @property
    def size_bytes(self) -> int:
        """
        返回对象大小，单位为字节。
        """
        return parse_size_string(self.size)


DEFAULT_DATA_OBJECT = DataLocalityObject(
    bucket="video-bucket",
    name="frame-seq-001",
    size="64M",
    storage_node="storage_near",
)


def build_storage_index(data_object: DataLocalityObject = DEFAULT_DATA_OBJECT) -> StorageIndex:
    """
    构造 StorageIndex。

    当前样例将对象放在 storage_near 节点上。该节点是存储专用节点，
    调度器默认不会把函数副本直接放到该节点，但会根据候选计算节点到该节点的网络距离打分。
    """
    storage_index = StorageIndex()
    storage_index.mb(data_object.bucket, data_object.storage_node)
    storage_index.put(
        DataItem(
            bucket=data_object.bucket,
            name=data_object.name,
            size=data_object.size_bytes,
        )
    )
    return storage_index
