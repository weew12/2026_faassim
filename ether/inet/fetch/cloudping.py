"""CloudPing 数据抓取文件，从 cloudping 公共接口获取 AWS 区域间延迟并转换为 Measurement。

================================================================================
架构定位 (Architecture)
================================================================================
本文件实现 cloudping 数据源:
    resource = 'https://api.cloudping.co/averages/day'
    fetch() -> List[Measurement]  ← 取过去 7 天平均延迟

对外接口(供 sources['cloudping'].fetch() 调用):
    fetch()           抓取并转 Measurement 列表
    _get_averages()   内部 HTTP 请求 (默认 7 天)

所有 fetch() 返回的 Measurement 由 inet/graph.py 的 add_to_graph
转成图边,写入 ether/inet/graphs/cloudping_<date>.graphml。
================================================================================
"""
from typing import List

import requests

from ether.inet.fetch.data import Measurement

resource = 'https://api.cloudping.co/averages/day'


def fetch() -> List[Measurement]:
    """
    从对应公网数据源抓取延迟测量并转换为统一 Measurement 列表。

    返回：统一 Measurement 列表。

    """
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
    """
    内部 HTTP 请求: GET https://api.cloudping.co/averages/day/<days>,返回 JSON。
    """
    url = f'{resource}/{days}'
    response = requests.get(url)

    if response.status_code != 200:
        raise RuntimeError(f'invalid response with code {response.status_code}')

    return response.json()
