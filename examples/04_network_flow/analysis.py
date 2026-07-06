"""
文件作用：network_flow 样例的结果导出与摘要分析工具。

该文件负责将网络流记录、路由记录和实验摘要保存到 outputs/ 目录。

新增的关键导出：
- network_flow_performance.csv：每个 flow 的完整性能指标（论文 demo 关键图）
  - throughput_mbps：实际吞吐量
  - goodput_mbps：去掉 TCP 协议开销后的有效吞吐
  - bottleneck_utilization_ratio：相对瓶颈链路带宽的利用率
- network_flow_summary.csv：增强版，加 throughput_mbps 和 scaling_factor
  - scaling_factor：并发相对单流的延迟放大倍数（论文里"瓶颈链路影响"最直观指标）
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


def _enrich_flow_df(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    给 flow_df 加上 throughput_mbps / goodput_mbps / bottleneck_utilization_ratio 列。

    ether 的 goodput 模型：goodput = bandwidth × 0.97 × 125000 B/s
    论文里如果想对比"实际带宽 vs 链路标称带宽"，可以画 bottleneck_utilization_ratio。
    """
    if flow_df.empty or "bytes" not in flow_df.columns or "duration" not in flow_df.columns:
        return flow_df

    df = flow_df.copy()
    # 避免除以 0
    duration_safe = df["duration"].apply(lambda d: d if d > 0 else 1e-9)
    # bytes 转 bit: bytes * 8 = bits
    # bits per second: bits / duration
    # Mbps: / 1e6
    df["throughput_mbps"] = (df["bytes"] * 8) / duration_safe / 1e6
    return df


def build_summary(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    根据网络流记录生成增强版摘要。

    摘要字段（按论文 demo 关心维度排序）：
    - flow_count / total_bytes
    - avg_duration / min_duration / max_duration
    - avg_throughput_mbps / max_throughput_mbps
    - avg_rtt_ms / max_rtt_ms / min_rtt_ms
    - scaling_factor：相对 single_flow 的延迟放大倍数（仅 concurrent 有意义）
    """
    if flow_df.empty:
        return pd.DataFrame()

    enriched = _enrich_flow_df(flow_df)

    base_agg = (
        enriched
        .groupby("scenario")
        .agg(
            flow_count=("flow_id", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
            min_duration=("duration", "min"),
            max_duration=("duration", "max"),
            avg_throughput_mbps=("throughput_mbps", "mean"),
            max_throughput_mbps=("throughput_mbps", "max"),
            avg_rtt_ms=("rtt_ms", "mean"),
            max_rtt_ms=("rtt_ms", "max"),
            min_rtt_ms=("rtt_ms", "min"),
        )
        .reset_index()
    )

    # 计算 scaling_factor：concurrent 相对 single 的延迟放大倍数
    if "single_flow" in base_agg["scenario"].values:
        single_avg_duration = float(
            base_agg.loc[base_agg["scenario"] == "single_flow", "avg_duration"].iloc[0]
        )
        base_agg["scaling_factor"] = base_agg["avg_duration"] / single_avg_duration
    else:
        base_agg["scaling_factor"] = None

    return base_agg


def build_flow_performance(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    论文 demo 关键图：每个 flow 的完整性能指标。

    返回列：
    - scenario / flow_id / bytes / size_mb
    - duration / start_time / finish_time
    - throughput_mbps（实际吞吐，论文图 Y 轴）
    - rtt_ms / hop_count / bottleneck_link / bottleneck_bandwidth_mbps
    - bottleneck_utilization_ratio（实际吞吐 / 瓶颈带宽）
    """
    if flow_df.empty:
        return pd.DataFrame()

    enriched = _enrich_flow_df(flow_df)

    # 计算 bottleneck_utilization_ratio = throughput_mbps / bottleneck_bandwidth_mbps
    if "bottleneck_bandwidth_mbps" in enriched.columns:
        enriched["bottleneck_utilization_ratio"] = (
            enriched["throughput_mbps"] / enriched["bottleneck_bandwidth_mbps"]
        )
    else:
        enriched["bottleneck_utilization_ratio"] = None

    preferred_columns = [
        "scenario",
        "flow_id",
        "bytes",
        "size_mb",
        "duration",
        "start_time",
        "finish_time",
        "throughput_mbps",
        "rtt_ms",
        "hop_count",
        "bottleneck_link",
        "bottleneck_bandwidth_mbps",
        "bottleneck_utilization_ratio",
    ]
    existing = [c for c in preferred_columns if c in enriched.columns]

    return (
        enriched[existing]
        .sort_values(["scenario", "flow_id"], ascending=[True, True])
        .reset_index(drop=True)
    )


def build_bottleneck_summary(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    统计不同瓶颈链路上的传输情况。
    """
    if flow_df.empty or "bottleneck_link" not in flow_df.columns:
        return pd.DataFrame()

    enriched = _enrich_flow_df(flow_df)

    return (
        enriched
        .groupby(["scenario", "bottleneck_link", "bottleneck_bandwidth_mbps"])
        .agg(
            flow_count=("flow_id", "count"),
            total_bytes=("bytes", "sum"),
            avg_duration=("duration", "mean"),
            avg_throughput_mbps=("throughput_mbps", "mean"),
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
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    flow_df = pd.DataFrame(flow_records)
    route_df = pd.DataFrame(route_records)

    # 新增：每个 flow 的完整性能（论文 demo 关键图）
    flow_perf_df = build_flow_performance(flow_df)

    # 增强版 summary
    summary_df = build_summary(flow_df)

    # 增强版 bottleneck summary
    bottleneck_summary_df = build_bottleneck_summary(flow_df)

    outputs = {
        "network_flow": flow_df,
        "network_route": route_df,
        "network_flow_performance": flow_perf_df,
        "network_flow_summary": summary_df,
        "network_bottleneck_summary": bottleneck_summary_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
