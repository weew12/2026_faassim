"""Ether 主机构造块文件，把节点工厂封装为 Host 单元，便于在拓扑单元中批量物化计算节点。"""

from typing import Callable

from ether.cell import Host
from ether.core import Node

Configurator = Callable[[Host], None]


def node_name(the_name: str) -> Configurator:
    """
    node_name 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。
    """
    def cfg(host: Host):
        """
        cfg 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。
        """
        node: Node = host.nodes[0]
        node.name = the_name

    return cfg


def as_host(node, *configurators: [Configurator]) -> Host:
    """
    as_host 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。
    """
    host = Host(node)

    for cfg in configurators:
        cfg(host)

    return host


def create_host(*configurators: [Configurator]):
    """
    创建当前模块约定的业务对象或拓扑构造块，并返回给上层场景使用。

    """
    node = Node('')

    return as_host(node, *configurators)


def main():

    """
    main 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。

    """
    def set_hostname_foo(host):
        """
        set_hostname_foo 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。
        """
        host.node.name = 'foo'

    def set_linkname(host):
        """
        set_linkname 函数的业务逻辑入口，负责完成当前模块中的对应处理步骤。
        """
        host.link.tags['name'] = 'link_%s' % host.node.name
        host.link.tags['hostname'] = host.node.name

    h = create_host(
        set_hostname_foo,
        set_linkname
    )

    print(h)


if __name__ == '__main__':
    main()
