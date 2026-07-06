"""
SimPy 内置子包聚合入口。

本文件把 faas-sim 最常使用的离散事件仿真对象汇总到 ``simpy`` 命名空间，包括
``Environment``、``Event``、``Timeout``、``Process``、共享资源、容器、存储队列和实时
环境。faas-sim 的核心流程依赖这些对象推进仿真时钟：函数部署通过 ``env.process``
启动生命周期进程，冷启动和执行耗时通过 ``env.timeout`` 表达，请求并发和资源争用
通过 Resource/Store/Container 等对象建模。

faas-sim 中的具体衔接点：
- ``sim.core.Environment`` 直接复用 ``simpy.Environment`` 的事件循环；
- ``sim.simulator`` 下的调度器、worker、监控循环都通过 ``env.process`` 启动；
- FaaS 请求队列通常建模为 ``Store`` 或 ``PriorityStore``；
- 副本并发槽通常建模为 ``Resource``（含抢占变体）。

本版本将用户上传的 SimPy 源码内置到项目根目录，用于替换原先通过 pip 安装的外部
``simpy==3.0.11`` 依赖。对 faas-sim 调用方而言，原有 ``import simpy`` 方式保持不变。
"""

from __future__ import annotations

import importlib.metadata
from typing import Tuple, Type

# 下面这一组 import 是公开 API 的真实定义来源。注意：这里只导入类型/类，不做任何
# 重命名或封装，因此调用方拿到的是与 simpy==3.0.11 完全一致的类对象。
from simpy.core import Environment
from simpy.events import AllOf, AnyOf, Event, Process, Timeout
from simpy.exceptions import Interrupt, SimPyException
from simpy.resources.container import Container
from simpy.resources.resource import PreemptiveResource, PriorityResource, Resource
from simpy.resources.store import FilterStore, PriorityItem, PriorityStore, Store
from simpy.rt import RealtimeEnvironment

# ``__all__`` 同时承担两个角色：
#   1. ``from simpy import *`` 时的白名单；
#   2. 与下面的 ``_toc`` 中的对象做一致性校验（见文件末尾的 ``assert``）。
# 任何新增的对外对象必须同时出现在 ``__all__`` 与 ``_toc`` 的合适分组中。
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
    根据公开类清单生成 Sphinx autosummary 目录文本。

    该函数只服务于模块 docstring，不参与 faas-sim 任何仿真流程。生成的目录会被
    ``.format(toc=...)`` 注入到 ``__doc__`` 末尾，让 ``help(simpy)`` 在终端直接打出
    漂亮的分组目录。
    """
    toc = ''
    for section, objs in entries:
        # 每节开头先插入一个空行（与上一节分隔），再输出节标题与下划线。
        toc += '\n\n'
        toc += f'{section}\n'
        toc += f'{section_marker * len(section)}\n\n'
        # autosummary 指令告诉 Sphinx 把后面的对象自动展开成简短描述。
        toc += '.. autosummary::\n\n'
        # ``~module.Name`` 表示 ``Name`` 不带模块前缀，方便排版。
        for obj in objs:
            toc += f'    ~{obj.__module__}.{obj.__name__}\n'
    return toc


# ``_toc`` 是公开对象按"语义类别"分组后的展示顺序。分组顺序也是文档中目录的顺序。
_toc = (
    (
        # 第一组：仿真环境。faas-sim 默认只使用 Environment；RealtimeEnvironment 保留
        # 给数字孪生 / 联调场景。
        'Environments',
        (
            Environment,
            RealtimeEnvironment,
        ),
    ),
    (
        # 第二组：事件与进程。这是 faas-sim 业务代码出现频率最高的类别。
        'Events',
        (
            Event,
            Timeout,
            Process,
            AllOf,
            AnyOf,
            # Interrupt 同时归入 Events 与 Exceptions：在生成器层面它表现为事件触发的
            # 异常抛出，在事件系统层面它是一个失败事件被 throw 进生成器。
            Interrupt,
        ),
    ),
    (
        # 第三组：共享资源。faas-sim 中 worker 池→Resource/PreemptiveResource，
        # 缓存水位→Container，请求队列→Store/PriorityStore/FilterStore。
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

# 使用 ``_toc`` 自动生成模块文档目录，确保公开对象清单与文档同步。
#   - ``__doc__`` 在模块加载时就已存在（最上面的三引号字符串）；
#   - ``__doc__.format(toc=...)`` 把 ``{toc}`` 占位符替换成真正的目录文本；
#   - ``assert`` 保证 ``__all__`` 与 ``_toc`` 涵盖的对象集合严格相等，防止漏列或拼写错误。
if __doc__:
    __doc__ = __doc__.format(toc=_compile_toc(_toc))
    assert set(__all__) == {obj.__name__ for _, objs in _toc for obj in objs}

try:
    # 优先从环境中的 simpy 发行包读取版本号（pip 安装时可用）。
    __version__ = importlib.metadata.version('simpy')
except importlib.metadata.PackageNotFoundError:
    # 以内置源码方式运行且未作为发行包安装时，提供一个可读的内置版本标识。
    # 这样 faas-sim 的日志系统能区分"用的内置 simpy"与"用的外部 simpy"。
    __version__ = 'embedded'