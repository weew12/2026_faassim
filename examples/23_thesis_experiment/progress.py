"""
文件作用：进度条兼容封装。
"""


def progress_iter(iterable, total=None, desc="progress"):
    """
    优先使用 tqdm 显示总览式进度条；缺失 tqdm 时使用原始迭代器。
    """
    try:
        from tqdm import tqdm

        return tqdm(
            iterable,
            total=total,
            desc=desc,
            unit="case",
            colour="white",
        )
    except Exception:
        return iterable
