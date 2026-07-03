"""互联网延迟数据抓取包入口，汇总多个公网延迟测量数据源。"""

from ether.inet.fetch import cloudping, gcloudping, wondernetwork
from ether.inet.fetch.data import Measurement

name = 'fetch'

# 可用互联网延迟抓取数据源映射。
sources = {
    'cloudping': cloudping,
    'gcloudping': gcloudping,
    'wondernetwork': wondernetwork
}

__all__ = [
    Measurement,
    sources
]
