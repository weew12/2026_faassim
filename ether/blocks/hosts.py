"""Ether 主机构造块文件，把节点工厂封装为 Host 单元，便于在拓扑单元中批量物化计算节点。

================================================================================
架构定位 (Architecture)
================================================================================
本文件是 ether 的【预置层】—— Configurator 模式工具。

提供函数式 Builder 模式,把"配置 Host 的步骤"封装成可复用的函数:
    Configurator = Callable[[Host], None]   # 配置器类型

    def node_name(name) -> Configurator:
        '''返回配置器: 把 host.node.name 设为 name'''

    def as_host(node, *configurators) -> Host:
        '''包成 Host, 顺序应用所有 configurators'''

    def create_host(*configurators) -> Host:
        '''创建匿名 Node, 配合 configurators 返回包好的 Host'''

设计哲学:
    1. 函数式 Builder: 用 *configurators 链式调, 替代构造参数爆炸
    2. 组合优于继承: 不需要"继承 Host 子类"就能加配置
    3. 易测试: 每个 configurator 是独立函数, 可单独单元测试
    4. 易扩展: 用户可以自定义 Configurator, 不用改 ether 源码

对比:
    # 继承式 (重)
    class MyHost(Host):
        def __init__(self):
            super().__init__(...)
            self.node.name = 'foo'
            self.link.tags['name'] = ...
            self.labels['gpu'] = 'true'
    # 函数式 (轻)
    as_host(node,
            node_name('foo'),
            set_linkname,
            add_label('gpu', 'true'))

对 CSAC 论文的接口:
    - 批量配置节点 (比如实验需要给一批节点打特定 label)
    - 自定义 Configurator (比如 add_label('csac_role', 'cache_origin'))
================================================================================
"""

from typing import Callable

from ether.cell import Host
from ether.core import Node

Configurator = Callable[[Host], None]


def node_name(the_name: str) -> Configurator:
    """
    返回一个 Configurator,把 host 的 node.name 设为 the_name。

    用法:  as_host(node, node_name('sensor_42'))
    """
    def cfg(host: Host):
        """
        实际配置函数: 修改 host.nodes[0].name。
        """
        node: Node = host.nodes[0]
        node.name = the_name

    return cfg


def as_host(node, *configurators: [Configurator]) -> Host:
    """
    把 node 包成 Host,按顺序应用所有 configurators。

    用法:  as_host(node, node_name('foo'), add_label('gpu', 'true'), ...)
    """
    host = Host(node)

    for cfg in configurators:
        cfg(host)

    return host


def create_host(*configurators: [Configurator]):
    """
    创建一个匿名 Node(空 name),返回包好的 Host。

    用法:  create_host(node_name('auto_42'), set_linkname)
    """
    node = Node('')

    return as_host(node, *configurators)


def main():

    """
    演示 Configurator 模式: set_hostname_foo + set_linkname 的组合用法。
    """
    def set_hostname_foo(host):
        """Configurator: 把 host.node.name 设为 'foo'"""
        host.node.name = 'foo'

    def set_linkname(host):
        """Configurator: 根据 hostname 同步 link 的 tags"""
        host.link.tags['name'] = 'link_%s' % host.node.name
        host.link.tags['hostname'] = host.node.name

    h = create_host(
        set_hostname_foo,
        set_linkname
    )

    print(h)


if __name__ == '__main__':
    main()
