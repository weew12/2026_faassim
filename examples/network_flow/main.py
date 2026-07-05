"""
文件作用：faas-sim / Ether 原生网络流样例。

本样例演示如何直接使用 Ether 的网络 Flow 模型，包括：
- 构建包含瓶颈链路的网络拓扑；
- 查询节点之间的 Route；
- 启动单个 Flow；
- 启动多个共享瓶颈链路的并发 Flow；
- 导出网络传输耗时和路由信息。

运行方式：
    python -u examples/network_flow/main.py
"""

import logging
import sys
from pathlib import Path

from analysis import export_outputs
from flow_runner import (
    collect_route_records,
    run_concurrent_bottleneck_scenario,
    run_single_flow_scenario,
)
from topology import build_network_flow_topology

logger = logging.getLogger(__name__)


def configure_logging():
    """
    配置日志输出。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def main():
    """
    network_flow 样例入口。
    """
    configure_logging()

    logger.info("building network flow topology")
    network = build_network_flow_topology()

    logger.info("collecting route records")
    route_records = collect_route_records(network)

    logger.info("running single flow scenario")
    single_records = run_single_flow_scenario(network)

    # 重新构建拓扑，避免单流场景结束后链路对象中残留状态影响并发场景。
    network = build_network_flow_topology()

    logger.info("running concurrent bottleneck scenario")
    concurrent_records = run_concurrent_bottleneck_scenario(network)

    flow_records = single_records + concurrent_records

    output_dir = Path(__file__).resolve().parent / "outputs"
    dfs = export_outputs(output_dir, flow_records, route_records)

    summary_df = dfs.get("network_flow_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("network flow summary:\\n%s", summary_df.to_string(index=False))

    bottleneck_df = dfs.get("network_bottleneck_summary")
    if bottleneck_df is not None and len(bottleneck_df) > 0:
        logger.info("network bottleneck summary:\\n%s", bottleneck_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
