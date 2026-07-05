"""
文件作用：执行 Ether 网络 Flow 仿真并生成结构化记录。

该文件不依赖 FaaS 函数部署流程，直接使用 Ether 的 Flow 模型，
用于更清楚地观察网络层自身的传输耗时和瓶颈链路竞争。
"""

import logging
from typing import Dict, List, Any

import simpy
from ether.core import Flow, Node, Link, Route
from skippy.core.utils import parse_size_string

logger = logging.getLogger(__name__)


def link_name(link: Link) -> str:
    """
    返回链路名称。

    如果链路 tags 中包含 name，则使用该名称；否则退化为对象字符串。
    """
    return link.tags.get("name", str(link))


def route_to_record(route: Route, route_name: str) -> Dict[str, Any]:
    """
    将 Route 对象转换为可导出的字典记录。
    """
    bottleneck = min(route.hops, key=lambda item: item.bandwidth) if route.hops else None

    return {
        "route_name": route_name,
        "source": route.source.name,
        "sink": route.destination.name,
        "rtt_ms": route.rtt,
        "hop_count": len(route.hops),
        "path": " -> ".join([getattr(item, "name", str(item)) for item in route.path]),
        "hops": " -> ".join([link_name(link) for link in route.hops]),
        "bottleneck_link": link_name(bottleneck) if bottleneck is not None else None,
        "bottleneck_bandwidth_mbps": bottleneck.bandwidth if bottleneck is not None else None,
    }


def transfer_process(
    env: simpy.Environment,
    topology,
    records: List[Dict[str, Any]],
    scenario: str,
    flow_id: str,
    source: Node,
    sink: Node,
    size_bytes: int,
    start_delay: float,
    action_type: str,
):
    """
    执行一次网络 Flow 传输。

    参数：
    - env：SimPy 仿真环境；
    - topology：Ether 拓扑；
    - records：用于收集结果的列表；
    - scenario：实验场景名；
    - flow_id：网络流标识；
    - source：源节点；
    - sink：目标节点；
    - size_bytes：传输数据大小；
    - start_delay：相对于仿真开始的启动时间；
    - action_type：业务类型，例如 image_pull / data_transfer。
    """
    yield env.timeout(start_delay)

    route = topology.route(source, sink)
    bottleneck = min(route.hops, key=lambda item: item.bandwidth)

    flow = Flow(env, size_bytes, route)

    start_time = env.now
    logger.info(
        "[simtime=%.4f] start flow=%s scenario=%s source=%s sink=%s bytes=%d bottleneck=%s(%sMbps)",
        start_time,
        flow_id,
        scenario,
        source.name,
        sink.name,
        size_bytes,
        link_name(bottleneck),
        bottleneck.bandwidth,
    )

    yield flow.start()

    finish_time = env.now
    duration = finish_time - start_time

    logger.info(
        "[simtime=%.4f] finish flow=%s duration=%.4fs",
        finish_time,
        flow_id,
        duration,
    )

    records.append({
        "scenario": scenario,
        "flow_id": flow_id,
        "action_type": action_type,
        "source": source.name,
        "sink": sink.name,
        "start_time": start_time,
        "finish_time": finish_time,
        "duration": duration,
        "bytes": size_bytes,
        "size_mb": size_bytes / 1000 / 1000,
        "rtt_ms": route.rtt,
        "hop_count": len(route.hops),
        "hops": " -> ".join([link_name(link) for link in route.hops]),
        "bottleneck_link": link_name(bottleneck),
        "bottleneck_bandwidth_mbps": bottleneck.bandwidth,
    })


def run_single_flow_scenario(network) -> List[Dict[str, Any]]:
    """
    运行单个 Flow 场景。

    该场景用于观察没有并发竞争时，一次边缘到云端传输需要多长时间。
    """
    env = simpy.Environment()
    records: List[Dict[str, Any]] = []

    env.process(
        transfer_process(
            env=env,
            topology=network.topology,
            records=records,
            scenario="single_flow",
            flow_id="single_a_to_cloud",
            source=network.nodes["edge_client_a"],
            sink=network.nodes["cloud_server"],
            size_bytes=parse_size_string("20M"),
            start_delay=0,
            action_type="data_transfer",
        )
    )

    env.run()
    return records


def run_concurrent_bottleneck_scenario(network) -> List[Dict[str, Any]]:
    """
    运行共享瓶颈链路并发 Flow 场景。

    该场景同时启动三个从不同边缘客户端到云端的传输。
    三个 Flow 都经过 bottleneck 链路，因此会触发 Ether 的带宽公平共享逻辑。
    """
    env = simpy.Environment()
    records: List[Dict[str, Any]] = []

    specs = [
        ("flow_a", "edge_client_a", "30M", 0.0),
        ("flow_b", "edge_client_b", "30M", 0.0),
        ("flow_c", "edge_client_c", "30M", 0.5),
    ]

    for flow_id, source_name, size, start_delay in specs:
        env.process(
            transfer_process(
                env=env,
                topology=network.topology,
                records=records,
                scenario="concurrent_bottleneck",
                flow_id=flow_id,
                source=network.nodes[source_name],
                sink=network.nodes["cloud_server"],
                size_bytes=parse_size_string(size),
                start_delay=start_delay,
                action_type="data_transfer",
            )
        )

    env.run()
    return records


def collect_route_records(network) -> List[Dict[str, Any]]:
    """
    收集样例中主要路由的静态信息。
    """
    route_records = []

    for source_name in ["edge_client_a", "edge_client_b", "edge_client_c"]:
        route = network.topology.route(network.nodes[source_name], network.nodes["cloud_server"])
        route_records.append(route_to_record(route, route_name=f"{source_name}_to_cloud"))

    return route_records
