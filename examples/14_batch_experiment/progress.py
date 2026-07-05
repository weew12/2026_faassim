"""
文件作用：批量实验进度条工具。

优先使用 tqdm 显示总览式进度条；如果本地环境没有安装 tqdm，则回退为普通迭代器。
"""

from typing import Iterable


def progress_iter(iterable: Iterable, total: int, description: str):
    """
    返回带进度显示的迭代器。

    参数：
    - iterable：待迭代对象；
    - total：总数量；
    - description：进度条说明。
    """
    try:
        from tqdm import tqdm

        return tqdm(
            iterable,
            total=total,
            desc=description,
            unit="run",
            colour="white",
        )
    except Exception:
        return iterable
