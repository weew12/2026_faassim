"""
文件作用：缓存状态快照读取与查询。

该文件把输入 CSV 中的节点级 warm 实例缓存状态转换为可查询索引，
供调度器在节点打分时使用。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


@dataclass(frozen=True)
class CacheEntry:
    """
    节点级函数缓存项。

    字段：
    - function_name：函数名称；
    - node_name：缓存所在节点；
    - warm_replicas：warm 副本数；
    - cached：是否存在有效缓存；
    - last_access_age：距离最近访问的时间；
    - avg_cold_start：平均冷启动耗时；
    - memory_units：缓存占用的抽象资源单位。
    """

    function_name: str
    node_name: str
    warm_replicas: int
    cached: bool
    last_access_age: float
    avg_cold_start: float
    memory_units: int


class CacheStateIndex:
    """
    函数缓存状态索引。

    支持按函数名查询所有 warm cache 节点，也支持判断某个节点是否命中目标函数缓存。
    """

    def __init__(self, entries: List[CacheEntry]):
        """
        初始化索引。
        """
        self.entries = entries
        self.by_function: Dict[str, List[CacheEntry]] = {}

        for entry in entries:
            if not entry.cached:
                continue
            self.by_function.setdefault(entry.function_name, []).append(entry)

    def entries_for_function(self, function_name: str) -> List[CacheEntry]:
        """
        返回指定函数的缓存项。
        """
        return list(self.by_function.get(function_name, []))

    def entry_for_node(self, function_name: str, node_name: str) -> Optional[CacheEntry]:
        """
        查询指定函数在指定节点上的缓存项。
        """
        for entry in self.by_function.get(function_name, []):
            if entry.node_name == node_name:
                return entry
        return None

    def has_cache(self, function_name: str, node_name: str) -> bool:
        """
        判断指定节点是否有目标函数 warm 缓存。
        """
        return self.entry_for_node(function_name, node_name) is not None

    def to_dataframe(self) -> pd.DataFrame:
        """
        返回缓存快照 DataFrame。
        """
        return pd.DataFrame([item.__dict__ for item in self.entries])


def load_cache_state(cache_path: Path) -> CacheStateIndex:
    """
    从 CSV 加载缓存状态快照。
    """
    cache_path = Path(cache_path)

    if not cache_path.exists():
        raise FileNotFoundError(f"cache state snapshot not found: {cache_path}")

    df = pd.read_csv(cache_path)

    required_columns = {
        "function_name",
        "node_name",
        "warm_replicas",
        "cached",
        "last_access_age",
        "avg_cold_start",
        "memory_units",
    }
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"cache state snapshot missing columns: {sorted(missing)}")

    entries: List[CacheEntry] = []

    for row in df.itertuples(index=False):
        cached_text = str(row.cached).strip().lower()
        cached = cached_text in {"true", "1", "yes", "y"}

        entries.append(
            CacheEntry(
                function_name=str(row.function_name),
                node_name=str(row.node_name),
                warm_replicas=int(row.warm_replicas),
                cached=cached,
                last_access_age=float(row.last_access_age),
                avg_cold_start=float(row.avg_cold_start),
                memory_units=int(row.memory_units),
            )
        )

    return CacheStateIndex(entries)
