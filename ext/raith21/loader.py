"""
文件作用：模型文件下载与加载辅助逻辑，处理性能退化模型等外部文件的获取和反序列化。
主要函数：load_model、download_with_progress。
在整体架构中的位置：属于 Raith21 论文实验扩展层，为异构设备、函数画像和调度策略提供可复现实验配置。
"""

import logging
import os

import joblib
import requests
from tqdm import tqdm

# 字段说明：logger：模块级日志记录器，用于输出当前模块的运行信息和调试信息。
logger = logging.getLogger(__name__)

# 字段说明：_urls：表示 urls，在当前业务流程中作为输入参数、状态字段或计算结果使用。
_urls = {
    'eb-jetson-nano-01.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-jetson-nano-01.sav',
    'eb-jetson-nx-01.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-jetson-nx-01.sav',
    'eb-jetson-tx2-01.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-jetson-tx2-01.sav',
    'eb-nuc7.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-nuc7.sav',
    'eb-rockpi.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-rockpi.sav',
    'eb-rpi3-01.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-rpi3-01.sav',
    'eb-rpi4-01.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-rpi4-01.sav',
    'eb-xeongpu.sav': 'https://owncloud.tuwien.ac.at/index.php/s/zpkdevN5kV36ewC/download?path=%2F&files=eb-xeongpu.sav',
}


def load_model(model_file: str):
    """
    函数作用：处理 load、model 相关业务逻辑。
    关键流程：
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    - 返回计算结果或被创建的业务对象，供上层流程继续使用。
    参数：model_file：表示 model、file，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    返回：与该业务步骤对应的对象、指标或计算结果。
    """
    d = os.path.dirname(model_file)
    if not os.path.isdir(d):
        logger.info('creating model folder %s', d)
        os.makedirs(d)

    if not os.path.isfile(model_file):
        file_name = os.path.basename(model_file)
        try:
            url = _urls[file_name]
        except KeyError:
            raise ValueError(f'could not download model file {file_name}, no remote url available')
        download_with_progress(url, model_file)

    return joblib.load(model_file)


def download_with_progress(url, target, block_size=2 ** 13):
    """
    函数作用：处理 download、with、progress 相关业务逻辑。
    关键流程：
    - 在约束不满足或状态非法时抛出异常，阻止仿真继续使用错误状态。
    参数：url：表示 url，在当前业务流程中作为输入参数、状态字段或计算结果使用。；target：表示 target，在当前业务流程中作为输入参数、状态字段或计算结果使用。；block_size：表示 block、size，在当前业务流程中作为输入参数、状态字段或计算结果使用。。
    返回：无显式返回值，主要通过对象状态、指标记录或仿真事件产生影响。
    """
    logger.info('downloading %s from %s', target, url)
    response = requests.get(url, stream=True)
    total_size_in_bytes = int(response.headers.get('content-length', 0))
    progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)

    with open(target, 'wb') as file:
        for data in response.iter_content(block_size):
            progress_bar.update(len(data))
            file.write(data)
    progress_bar.close()

    if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
        raise IOError('error downloading file')
