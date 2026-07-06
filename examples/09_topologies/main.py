"""
文件作用：faas-sim / Ether 拓扑构建样例。

本样例演示 examples/topologies 中常见拓扑构造方式，包括：
- 最小二节点拓扑；
- 边缘-云星型拓扑；
- 共享瓶颈链路拓扑；
- 官方 UrbanSensingScenario 拓扑；
- 节点、边、路由和摘要结果导出。

运行方式：
    python -u examples/09_topologies/main.py
"""

import logging
import sys
from pathlib import Path

from analysis import export_outputs
from topology_builders import build_all_topology_cases

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
    topologies 样例入口。
    """
    configure_logging()

    logger.info("building topology cases")
    topology_cases = build_all_topology_cases()

    for case in topology_cases:
        logger.info(
            "built topology=%s, explicit_nodes=%d, explicit_links=%d, description=%s",
            case.name,
            len(case.nodes),
            len(case.links),
            case.description,
        )

    output_dir = Path(__file__).resolve().parent / "outputs"
    outputs = export_outputs(topology_cases, output_dir)

    summary_df = outputs.get("topology_summary")
    if summary_df is not None and len(summary_df) > 0:
        logger.info("topology summary:\\n%s", summary_df.to_string(index=False))

    logger.info("outputs saved to %s", output_dir)


if __name__ == "__main__":
    main()
