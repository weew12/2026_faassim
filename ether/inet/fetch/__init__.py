"""互联网延迟数据抓取包入口，汇总多个公网延迟测量数据源。

================================================================================
架构定位 (Architecture)
================================================================================
本子包提供【3 个公网数据源的统一入口】:
    - cloudping     (AWS 区域)        https://api.cloudping.co/averages/day
    - gcloudping    (GCP 区域)
    - wondernetwork (广域)

每个模块都实现 fetch() -> List[Measurement] 接口,
通过 sources 字典统一注册,供 cli/inet.py 和用户程序并发调用。
"""

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
