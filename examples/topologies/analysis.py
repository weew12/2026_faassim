"""
文件作用：topologies 样例的结果导出工具。

该文件负责汇总多个拓扑的节点、边、路由和摘要信息，并保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from inspectors import (
    collect_graph_nodes,
    collect_graph_edges,
    collect_route_records,
    build_topology_summary,
)

logger = logging.getLogger(__name__)


def export_outputs(topology_cases, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出拓扑样例结果。

    输出文件：
    - topology_nodes.csv
    - topology_edges.csv
    - topology_routes.csv
    - topology_summary.csv
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    node_frames: List[pd.DataFrame] = []
    edge_frames: List[pd.DataFrame] = []
    route_frames: List[pd.DataFrame] = []
    summary_records = []

    for topology_case in topology_cases:
        logger.info("inspecting topology case: %s", topology_case.name)

        node_df = collect_graph_nodes(topology_case)
        edge_df = collect_graph_edges(topology_case)
        route_df = collect_route_records(topology_case)

        node_frames.append(node_df)
        edge_frames.append(edge_df)
        route_frames.append(route_df)

        summary_records.append(
            build_topology_summary(
                topology_case=topology_case,
                node_df=node_df,
                edge_df=edge_df,
                route_df=route_df,
            )
        )

    outputs = {
        "topology_nodes": pd.concat(node_frames, ignore_index=True) if node_frames else pd.DataFrame(),
        "topology_edges": pd.concat(edge_frames, ignore_index=True) if edge_frames else pd.DataFrame(),
        "topology_routes": pd.concat(route_frames, ignore_index=True) if route_frames else pd.DataFrame(),
        "topology_summary": pd.DataFrame(summary_records),
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
