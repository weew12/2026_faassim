"""
文件作用：topologies 样例的结果导出工具。

该文件负责汇总多个拓扑的节点、边、路由和摘要信息，并保存到 outputs/ 目录。

新增的关键导出（沿用 02-08 的 paper_highlight / data_self_check 模式）：
- topology_paper_highlight.csv：
    每条论文 demo 关键摘要对应一行 metric/value（14 条）
- topology_self_check.csv：
    10 项数据自检（PASS/FAIL）
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


def build_paper_highlight(
    summary_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    routes_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02-08 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if summary_df.empty:
        return pd.DataFrame([
            {"metric": "total_topologies", "value": 0,
             "note": "构建的拓扑样例总数"},
        ])

    total_topologies = int(len(summary_df))

    # 总节点 / 边 / 路由数
    total_graph_nodes = int(summary_df["graph_node_count"].sum())
    total_graph_edges = int(summary_df["graph_edge_count"].sum())
    total_route_records = int(summary_df["route_records"].sum())

    # urban_sensing 最大
    urban_sensing_row = summary_df[summary_df["topology"] == "urban_sensing"]
    if not urban_sensing_row.empty:
        urban_nodes = int(urban_sensing_row["graph_node_count"].iloc[0])
        urban_edges = int(urban_sensing_row["graph_edge_count"].iloc[0])
        urban_routes = int(urban_sensing_row["route_records"].iloc[0])
    else:
        urban_nodes = urban_edges = urban_routes = 0

    # minimal 最小
    minimal_row = summary_df[summary_df["topology"] == "minimal"]
    if not minimal_row.empty:
        minimal_nodes = int(minimal_row["graph_node_count"].iloc[0])
        minimal_edges = int(minimal_row["graph_edge_count"].iloc[0])
    else:
        minimal_nodes = minimal_edges = 0

    # scaling factor
    scaling_factor = urban_nodes / minimal_nodes if minimal_nodes > 0 else 0.0

    # 路由 RTT / hop_count 统计
    if not routes_df.empty and "rtt_ms" in routes_df.columns:
        valid_routes = routes_df[routes_df["route_available"] == True] if "route_available" in routes_df.columns else routes_df
        avg_rtt = float(valid_routes["rtt_ms"].mean()) if "rtt_ms" in valid_routes.columns and len(valid_routes) > 0 else 0.0
        max_rtt = float(valid_routes["rtt_ms"].max()) if "rtt_ms" in valid_routes.columns and len(valid_routes) > 0 else 0.0
        avg_hops = float(valid_routes["hop_count"].mean()) if "hop_count" in valid_routes.columns and len(valid_routes) > 0 else 0.0
        max_hops = int(valid_routes["hop_count"].max()) if "hop_count" in valid_routes.columns and len(valid_routes) > 0 else 0
        route_success_count = int(valid_routes.shape[0]) if "route_available" in routes_df.columns else int(routes_df.shape[0])
        route_failure_count = total_route_records - route_success_count
    else:
        avg_rtt = max_rtt = avg_hops = 0.0
        max_hops = 0
        route_success_count = 0
        route_failure_count = 0

    return pd.DataFrame([
        {"metric": "total_topologies", "value": total_topologies,
         "note": "构建的拓扑样例总数（minimal/edge_cloud_star/bottleneck/urban_sensing）"},
        {"metric": "total_graph_nodes", "value": total_graph_nodes,
         "note": "4 个拓扑的图节点总数"},
        {"metric": "total_graph_edges", "value": total_graph_edges,
         "note": "4 个拓扑的图边总数（有向边）"},
        {"metric": "total_route_records", "value": total_route_records,
         "note": "4 个拓扑的 route 总数"},
        {"metric": "minimal_graph_nodes", "value": minimal_nodes,
         "note": "minimal 拓扑的图节点数"},
        {"metric": "urban_sensing_graph_nodes", "value": urban_nodes,
         "note": "urban_sensing 拓扑的图节点数（最大）"},
        {"metric": "urban_sensing_graph_edges", "value": urban_edges,
         "note": "urban_sensing 拓扑的图边数"},
        {"metric": "size_scaling_minimal_to_urban", "value": round(scaling_factor, 4),
         "note": "urban_sensing 节点数 / minimal 节点数（论文 demo 关键比值）"},
        {"metric": "avg_route_rtt_ms", "value": round(avg_rtt, 4),
         "note": "所有成功路由的平均 RTT（ms）"},
        {"metric": "max_route_rtt_ms", "value": round(max_rtt, 4),
         "note": "所有成功路由的最大 RTT（ms）"},
        {"metric": "avg_route_hop_count", "value": round(avg_hops, 4),
         "note": "所有成功路由的平均 hop 数"},
        {"metric": "max_route_hop_count", "value": max_hops,
         "note": "所有成功路由的最大 hop 数"},
        {"metric": "route_success_count", "value": route_success_count,
         "note": "成功的 route 数（route_available == True）"},
        {"metric": "route_failure_count", "value": route_failure_count,
         "note": "失败的 route 数"},
    ])


def data_self_check(
    summary_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    routes_df: pd.DataFrame,
    paper_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    topology 样例的数据自洽检查（沿用 02-08 的 self_check 模式）。

    不变量：
    1. total_topologies == 4
    2. 每个拓扑的 graph_node_count > 0
    3. 每个拓扑的 graph_edge_count > 0
    4. topology_edges 总行数 == summary.graph_edge_count 之和
    5. topology_routes 总行数 == summary.route_records 之和
    6. urban_sensing 能查到路由（>= 1）
    7. 所有 topology 至少有 1 个 route
    8. nodes 总行数 == summary.graph_node_count 之和
    9. routes 列名包含关键字段
    10. paper 与 summary 自洽

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if summary_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    total_topologies = int(len(summary_df))

    all_nodes_positive = bool((summary_df["graph_node_count"] > 0).all())
    all_edges_positive = bool((summary_df["graph_edge_count"] > 0).all())

    edges_total = int(len(edges_df))
    routes_total = int(len(routes_df))
    nodes_total = int(len(nodes_df))

    summary_edges_sum = int(summary_df["graph_edge_count"].sum())
    summary_routes_sum = int(summary_df["route_records"].sum())
    summary_nodes_sum = int(summary_df["graph_node_count"].sum())

    urban_sensing_success_count = 0
    if not routes_df.empty and "topology" in routes_df.columns:
        urban_routes = routes_df[routes_df["topology"] == "urban_sensing"]
        if "route_available" in urban_routes.columns:
            urban_sensing_success_count = int((urban_routes["route_available"] == True).sum())
        else:
            urban_sensing_success_count = int(urban_routes.shape[0])

    if not routes_df.empty and {"topology", "route_available"}.issubset(routes_df.columns):
        success_by_topology = (
            routes_df[routes_df["route_available"] == True]
            .groupby("topology")
            .size()
        )
        all_topology_has_route = all(
            int(success_by_topology.get(topology_name, 0)) >= 1
            for topology_name in summary_df["topology"]
        )
    else:
        all_topology_has_route = bool((summary_df["route_records"] >= 1).all())

    routes_columns = set(routes_df.columns.astype(str).tolist()) if not routes_df.empty else set()
    required_columns = {"topology", "source", "sink"}
    routes_has_required = required_columns.issubset(routes_columns)

    # paper self-consistent
    paper_total_topologies = -1
    paper_total_nodes = -1
    paper_total_routes = -1
    if not paper_df.empty:
        total_row = paper_df[paper_df["metric"] == "total_topologies"]
        nodes_row = paper_df[paper_df["metric"] == "total_graph_nodes"]
        routes_row = paper_df[paper_df["metric"] == "total_route_records"]
        if not total_row.empty:
            paper_total_topologies = int(total_row["value"].iloc[0])
        if not nodes_row.empty:
            paper_total_nodes = int(nodes_row["value"].iloc[0])
        if not routes_row.empty:
            paper_total_routes = int(routes_row["value"].iloc[0])

    paper_consistent = (
        paper_total_topologies == total_topologies
        and paper_total_nodes == summary_nodes_sum
        and paper_total_routes == summary_routes_sum
    )

    checks = {
        "01_total_topologies_is_4": total_topologies == 4,
        "02_all_nodes_positive": all_nodes_positive,
        "03_all_edges_positive": all_edges_positive,
        "04_edges_total_matches_summary": edges_total == summary_edges_sum,
        "05_routes_total_matches_summary": routes_total == summary_routes_sum,
        "06_urban_sensing_has_routes": urban_sensing_success_count >= 1,
        "07_all_topology_has_routes": all_topology_has_route,
        "08_nodes_total_matches_summary": nodes_total == summary_nodes_sum,
        "09_routes_has_required_columns": bool(routes_has_required),
        "10_paper_self_consistent": bool(paper_consistent),
    }

    return checks


def export_outputs(topology_cases, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出拓扑样例结果。

    输出文件：
    - topology_nodes.csv
    - topology_edges.csv
    - topology_routes.csv
    - topology_summary.csv
    - topology_paper_highlight.csv
    - topology_self_check.csv
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

    summary_df = pd.DataFrame(summary_records)

    nodes_combined = pd.concat(node_frames, ignore_index=True) if node_frames else pd.DataFrame()
    edges_combined = pd.concat(edge_frames, ignore_index=True) if edge_frames else pd.DataFrame()
    routes_combined = pd.concat(route_frames, ignore_index=True) if route_frames else pd.DataFrame()

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        summary_df=summary_df,
        nodes_df=nodes_combined,
        edges_df=edges_combined,
        routes_df=routes_combined,
    )

    # 数据自检
    checks = data_self_check(
        summary_df=summary_df,
        nodes_df=nodes_combined,
        edges_df=edges_combined,
        routes_df=routes_combined,
        paper_df=paper_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])

    outputs = {
        "topology_nodes": nodes_combined,
        "topology_edges": edges_combined,
        "topology_routes": routes_combined,
        "topology_summary": summary_df,
        "topology_paper_highlight": paper_df,
        "topology_self_check": check_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
