"""
SimPy 内置子包聚合入口。

本文件把 faas-sim 最常使用的离散事件仿真对象汇总到 ``simpy`` 命名空间，包括
``Environment``、``Event``、``Timeout``、``Process``、共享资源、容器、存储队列和实时
环境。faas-sim 的核心流程依赖这些对象推进仿真时钟：函数部署通过 ``env.process``
启动生命周期进程，冷启动和执行耗时通过 ``env.timeout`` 表达，请求并发和资源争用
通过 Resource/Store/Container 等对象建模。

本版本将用户上传的 SimPy 源码内置到项目根目录，用于替换原先通过 pip 安装的外部
``simpy==3.0.11`` 依赖。对 faas-sim 调用方而言，原有 ``import simpy`` 方式保持不变。
"""

from __future__ import annotations

import importlib.metadata
from typing import Tuple, Type

from simpy.core import Environment
from simpy.events import AllOf, AnyOf, Event, Process, Timeout
from simpy.exceptions import Interrupt, SimPyException
from simpy.resources.container import Container
from simpy.resources.resource import PreemptiveResource, PriorityResource, Resource
from simpy.resources.store import FilterStore, PriorityItem, PriorityStore, Store
from simpy.rt import RealtimeEnvironment

__all__ = [
    'AllOf',
    'AnyOf',
    'Container',
    'Environment',
    'Event',
    'FilterStore',
    'Interrupt',
    'PreemptiveResource',
    'PriorityItem',
    'PriorityResource',
    'PriorityStore',
    'Process',
    'RealtimeEnvironment',
    'Resource',
    'SimPyException',
    'Store',
    'Timeout',
]


def _compile_toc(
    entries: Tuple[Tuple[str, Tuple[Type, ...]], ...],
    section_marker: str = '=',
) -> str:
    """
    根据公开类清单生成 Sphinx autosummary 目录文本。该函数只服务于文档字符串，不参与 faas-sim 仿真流程。
    """
    toc = ''
    for section, objs in entries:
        toc += '\n\n'
        toc += f'{section}\n'
        toc += f'{section_marker * len(section)}\n\n'
        toc += '.. autosummary::\n\n'
        for obj in objs:
            toc += f'    ~{obj.__module__}.{obj.__name__}\n'
    return toc


_toc = (
    (
        'Environments',
        (
            Environment,
            RealtimeEnvironment,
        ),
    ),
    (
        'Events',
        (
            Event,
            Timeout,
            Process,
            AllOf,
            AnyOf,
            Interrupt,
        ),
    ),
    (
        'Resources',
        (
            Resource,
            PriorityResource,
            PreemptiveResource,
            Container,
            Store,
            PriorityItem,
            PriorityStore,
            FilterStore,
        ),
    ),
    ('Exceptions', (SimPyException, Interrupt)),
)

# 使用 _toc 自动生成模块文档目录，确保公开对象清单与文档同步。
if __doc__:
    __doc__ = __doc__.format(toc=_compile_toc(_toc))
    assert set(__all__) == {obj.__name__ for _, objs in _toc for obj in objs}

try:
    __version__ = importlib.metadata.version('simpy')
except importlib.metadata.PackageNotFoundError:
    # 以内置源码方式运行且未作为发行包安装时，提供一个可读的内置版本标识。
    __version__ = 'embedded'
