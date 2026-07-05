"""
文件作用：network_flow 样例的结果导出与摘要分析工具。

该文件负责将网络流记录、路由记录和实验摘要保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


def build_summary(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    根据网络流记录生成摘要。

    摘要按 scenario 分组，统计：
    - flow 数量；
    - 总传输字节数；
    - 平均传输时间；
    - 最大传输时间；
    - 最小传输时间。
    """
    if flow_df.empty:
        return pd.DataFrame()

    return (
        flow_df
        .groupby("scenario")
        .agg(
            flow_count=("flow_id", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
            min_duration=("duration", "min"),
            max_duration=("duration", "max"),
            avg_rtt_ms=("rtt_ms", "mean"),
        )
        .reset_index()
    )


def build_bottleneck_summary(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    统计不同瓶颈链路上的传输情况。
    """
    if flow_df.empty or "bottleneck_link" not in flow_df.columns:
        return pd.DataFrame()

    return (
        flow_df
        .groupby(["scenario", "bottleneck_link", "bottleneck_bandwidth_mbps"])
        .agg(
            flow_count=("flow_id", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
        )
        .reset_index()
    )


def export_outputs(
    output_dir: Path,
    flow_records: List[Dict[str, Any]],
    route_records: List[Dict[str, Any]],
) -> Dict[str, pd.DataFrame]:
    """
    导出 network_flow 样例结果。

    参数：
    - output_dir：输出目录；
    - flow_records：网络流记录；
    - route_records：路由记录。

    返回：
    - Dict[str, DataFrame]：导出的结果表。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    flow_df = pd.DataFrame(flow_records)
    route_df = pd.DataFrame(route_records)
    summary_df = build_summary(flow_df)
    bottleneck_summary_df = build_bottleneck_summary(flow_df)

    outputs = {
        "network_flow": flow_df,
        "network_route": route_df,
        "network_flow_summary": summary_df,
        "network_bottleneck_summary": bottleneck_summary_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
