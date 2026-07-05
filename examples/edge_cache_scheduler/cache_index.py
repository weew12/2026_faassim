"""
文件作用：边缘缓存状态索引。

缓存类型包括：
- function：函数 warm 实例缓存；
- image：函数镜像缓存；
- data：函数输入数据缓存。
"""

from typing import Dict, Iterable, Optional, Tuple

from models import CacheEntry


class EdgeCacheIndex:
    """
    边缘缓存状态索引。
    """

    def __init__(self, entries: Iterable[CacheEntry]):
        """
        初始化索引。
        """
        self.entries: Dict[Tuple[str, str, str], CacheEntry] = {}

        for entry in entries:
            if not entry.cached:
                continue
            self.entries[(entry.cache_type, entry.cache_key, entry.node_name)] = entry

    def get(self, cache_type: str, cache_key: str, node_name: str) -> Optional[CacheEntry]:
        """
        查询缓存项。
        """
        return self.entries.get((cache_type, cache_key, node_name))

    def has(self, cache_type: str, cache_key: str, node_name: str) -> bool:
        """
        判断缓存是否命中。
        """
        return self.get(cache_type, cache_key, node_name) is not None

    def freshness(self, cache_type: str, cache_key: str, node_name: str) -> float:
        """
        查询缓存新鲜度。
        """
        entry = self.get(cache_type, cache_key, node_name)
        if entry is None:
            return 0.0
        return entry.freshness

    def warm_function(self, function_name: str, node_name: str, freshness: float = 1.0):
        """
        写入函数 warm 实例缓存。

        请求被调度到某节点后，该节点会形成或刷新该函数的 warm 缓存。
        """
        self.entries[("function", function_name, node_name)] = CacheEntry(
            cache_type="function",
            cache_key=function_name,
            node_name=node_name,
            cached=True,
            freshness=freshness,
        )

    def cache_image_and_data(self, function_name: str, node_name: str, freshness: float = 1.0):
        """
        写入镜像缓存和数据缓存。

        该方法用于模拟请求执行后节点侧缓存状态的演化。
        """
        for cache_type in ["image", "data"]:
            self.entries[(cache_type, function_name, node_name)] = CacheEntry(
                cache_type=cache_type,
                cache_key=function_name,
                node_name=node_name,
                cached=True,
                freshness=freshness,
            )
