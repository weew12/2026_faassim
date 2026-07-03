"""GCloudPing 数据抓取文件，从 gcloudping 公共接口获取 Google Cloud 区域间延迟并转换为 Measurement。"""

from typing import List

import requests

from ether.inet.fetch.data import Measurement

# the API IP may change, it's called by http://gcloudping.com/
resource = 'http://35.202.190.222/api/latencies/matrix'


def fetch() -> List[Measurement]:
    """
    从对应公网数据源抓取延迟测量并转换为统一 Measurement 列表。

    返回：统一 Measurement 列表。

    """
    json = _query()

    regions = json['regions']
    latencies = json['latencies']

    result = list()

    for from_id, to_items in enumerate(latencies):
        for to_id, value in enumerate(to_items):
            if value is None:
                continue

            result.append(Measurement(
                regions[from_id],
                regions[to_id],
                value
            ))

    return result


def _query():
    """
    内部辅助方法，服务于当前模块的主要业务流程。

    """
    response = requests.get(resource)

    if response.status_code != 200:
        raise RuntimeError(f'invalid response with code {response.status_code}')

    return response.json()
