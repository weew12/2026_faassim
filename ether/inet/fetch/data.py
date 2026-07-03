"""互联网延迟测量数据结构文件，定义区域到区域延迟样本的统一表示。"""

from typing import NamedTuple


class Measurement(NamedTuple):
    """互联网延迟测量记录，保存源区域、目标区域和测得的延迟值。"""
    # 连接、路由或流的源节点。
    source: str
    # 路由或流量传输的目标节点。
    destination: str

    avg: float
    max: float = -1
    min: float = -1
