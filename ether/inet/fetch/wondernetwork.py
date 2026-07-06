"""WonderNetwork 数据抓取文件，从 wondernetwork 数据源获取全球城市间延迟并转换为 Measurement。

================================================================================
架构定位 (Architecture)
================================================================================
本文件实现 wondernetwork (全球城市间) 数据源:
    resource = 'https://wondernetwork.com/ping-data'
    regions = [4, 5, 6, ...]   ← region_id 列表
    fetch() -> List[Measurement]

数据格式 (跟前两个不同):
    POST 请求, params = {sources: regions, destinations: regions}
    返回 JSON 包含 'pingData' (嵌套字典 {from_region: {to_region: measurement}})

对外接口(供 sources['wondernetwork'].fetch() 调用):
    fetch()              抓取并转 Measurement 列表
    _query(region_ids)   内部 HTTP 请求
    _get_json(params)    底层 HTTP 封装
    _parse_measurement() JSON 单条转 Measurement
================================================================================
"""

from typing import Dict, List

import requests

from ether.inet.fetch.data import Measurement

resource = 'https://wondernetwork.com/ping-data'

regions = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 26, 37, 208, 67, 47, 50, 96, 43, 200, 22, 104, 91, 19, 153, 60, 66, 34,
           244, 108]


def fetch() -> List[Measurement]:
    """
    从对应公网数据源抓取延迟测量并转换为统一 Measurement 列表。

    返回：统一 Measurement 列表。

    """
    return _query(regions)


def _query(region_ids) -> List[Measurement]:
    """
    内部方法: 调 wondernetwork API,遍历 pingData 嵌套字典,转 Measurement 列表。
    """
    regions_encoded = ','.join(map(str, region_ids))
    json = _get_json({'sources': regions_encoded, 'destinations': regions_encoded})
    data = json['pingData']

    result = list()

    for from_regions, to_regions in data.items():
        for _, measurement in to_regions.items():
            result.append(_parse_measurement(measurement))

    return result


def _get_json(params):
    """
    底层 HTTP 封装: GET wondernetwork.com/ping-data,失败时抛 RuntimeError。
    """
    response = requests.get(resource, params)

    if response.status_code != 200 and response.json():
        raise RuntimeError(f'invalid response with code {response.status_code}')

    return response.json()


def _parse_measurement(data: Dict) -> Measurement:
    """
    把 wondernetwork 的单条 JSON 数据 (含 avg/max/min/source_name/destination_name) 转 Measurement。
    """
    return Measurement(
        avg=float(data['avg']),
        max=float(data['max']),
        min=float(data['min']),
        source=data['source_name'],
        destination=data['destination_name']
    )
