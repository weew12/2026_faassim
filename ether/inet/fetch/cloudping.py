"""CloudPing 数据抓取文件，从 cloudping 公共接口获取 AWS 区域间延迟并转换为 Measurement。"""

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
    内部辅助方法，服务于当前模块的主要业务流程。
    """
    url = f'{resource}/{days}'
    response = requests.get(url)

    if response.status_code != 200:
        raise RuntimeError(f'invalid response with code {response.status_code}')

    return response.json()
