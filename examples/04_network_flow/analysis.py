"""
文件作用：network_flow 样例的结果导出与摘要分析工具。

该文件负责将网络流记录、路由记录和实验摘要保存到 outputs/ 目录。

新增的关键导出：
- network_flow_performance.csv：每个 flow 的完整性能指标（论文 demo 关键图）
  - throughput_mbps：实际吞吐量
  - bottleneck_fraction_of_link：单条 flow 吞吐 / 瓶颈链路标称带宽
- network_flow_summary.csv：增强版，加 throughput_mbps 和 scaling_factor
  - scaling_factor：同大小 flow 下，并发相对单流的延迟放大倍数
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)

SCENARIO_ORDER = {
    "single_flow": 0,
    "concurrent_bottleneck": 1,
}


def _enrich_flow_df(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    给 flow_df 加上 throughput_mbps 列。
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

    base_agg["_scenario_order"] = base_agg["scenario"].map(SCENARIO_ORDER).fillna(99)
    return (
        base_agg
        .sort_values("_scenario_order")
        .drop(columns=["_scenario_order"])
        .reset_index(drop=True)
    )


def build_flow_performance(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    论文 demo 关键图：每个 flow 的完整性能指标。

    返回列：
    - scenario / flow_id / bytes / size_mb
    - duration / start_time / finish_time
    - throughput_mbps（实际吞吐，论文图 Y 轴）
    - rtt_ms / hop_count / bottleneck_link / bottleneck_bandwidth_mbps
    - bottleneck_fraction_of_link（实际吞吐 / 瓶颈带宽）
    """
    if flow_df.empty:
        return pd.DataFrame()

    enriched = _enrich_flow_df(flow_df)

    # 单条 flow 占用瓶颈链路标称带宽的比例。
    if "bottleneck_bandwidth_mbps" in enriched.columns:
        enriched["bottleneck_fraction_of_link"] = (
            enriched["throughput_mbps"] / enriched["bottleneck_bandwidth_mbps"]
        )
    else:
        enriched["bottleneck_fraction_of_link"] = None

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
        "bottleneck_fraction_of_link",
    ]
    existing = [c for c in preferred_columns if c in enriched.columns]

    out = enriched[existing].copy()
    out["_scenario_order"] = out["scenario"].map(SCENARIO_ORDER).fillna(99)
    out = (
        out
        .sort_values(["_scenario_order", "flow_id"], ascending=[True, True])
        .drop(columns=["_scenario_order"])
        .reset_index(drop=True)
    )
    return out


def build_bottleneck_summary(flow_df: pd.DataFrame) -> pd.DataFrame:
    """
    统计不同瓶颈链路上的传输情况。
    """
    if flow_df.empty or "bottleneck_link" not in flow_df.columns:
        return pd.DataFrame()

    enriched = _enrich_flow_df(flow_df)

    out = (
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
    out["_scenario_order"] = out["scenario"].map(SCENARIO_ORDER).fillna(99)
    return (
        out
        .sort_values(["_scenario_order", "bottleneck_link"])
        .drop(columns=["_scenario_order"])
        .reset_index(drop=True)
    )


def build_paper_highlight(
    flow_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    bottleneck_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要：每条论文宣传语都对应一行 metric/value。

    设计原则（沿用 02_load_balancer / 03_skippy_scheduler 的 paper_highlight 模式）：
    1. metric 字段是论文能直接引用的实证数字；
    2. value 字段是机器可读的具体数值；
    3. note 字段是 paper-style 一句话结论。

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    # 兜底：flow_df 为空时返回仅一行 False 的占位
    if flow_df.empty:
        return pd.DataFrame([
            {"metric": "single_flow_throughput_mbps", "value": 0.0,
             "note": "单流吞吐量（Mbps）"},
            {"metric": "concurrent_flow_throughput_mbps", "value": 0.0,
             "note": "并发平均吞吐量（Mbps）"},
            {"metric": "scaling_factor", "value": 0.0,
             "note": "并发相对单流的延迟放大倍数"},
        ])

    enriched = _enrich_flow_df(flow_df)

    # 按 scenario 切分
    single_df = enriched[enriched["scenario"] == "single_flow"]
    concurrent_df = enriched[enriched["scenario"] == "concurrent_bottleneck"]

    # 单流吞吐（== 瓶颈链路带宽利用率上限）
    single_tp = float(single_df["throughput_mbps"].mean()) if not single_df.empty else 0.0
    single_duration = float(single_df["duration"].mean()) if not single_df.empty else 0.0

    # 并发吞吐
    concurrent_tp = float(concurrent_df["throughput_mbps"].mean()) if not concurrent_df.empty else 0.0
    concurrent_duration = float(concurrent_df["duration"].mean()) if not concurrent_df.empty else 0.0
    concurrent_flow_count = int(len(concurrent_df))

    # scaling_factor：同大小 flow 下，并发相对单流的延迟放大倍数
    scaling_factor = concurrent_duration / single_duration if single_duration > 0 else 0.0

    # 瓶颈链路利用率
    bottleneck_bandwidth = float(concurrent_df["bottleneck_bandwidth_mbps"].iloc[0]) \
        if not concurrent_df.empty and "bottleneck_bandwidth_mbps" in concurrent_df.columns else 0.0
    bottleneck_share = bottleneck_bandwidth / concurrent_flow_count if concurrent_flow_count > 0 else 0.0
    fair_share_utilization = concurrent_tp / bottleneck_share if bottleneck_share > 0 else 0.0

    # 公平性：3 个并发流的 throughput 标准差（越小越公平）
    if not concurrent_df.empty and len(concurrent_df) > 1:
        throughput_std = float(concurrent_df["throughput_mbps"].std(ddof=0))
    else:
        throughput_std = 0.0

    # 路由一致性：所有 flow 是否走同一 bottleneck
    all_same_bottleneck = False
    if "bottleneck_link" in enriched.columns and len(enriched) > 0:
        all_same_bottleneck = bool(enriched["bottleneck_link"].nunique() == 1)

    return pd.DataFrame([
        {"metric": "single_flow_throughput_mbps", "value": round(single_tp, 4),
         "note": "单流吞吐量（Mbps），应接近 bottleneck 链路标称带宽"},
        {"metric": "single_flow_duration_s", "value": round(single_duration, 4),
         "note": "单流 30M 传输耗时（秒），无竞争基线"},
        {"metric": "concurrent_flow_count", "value": concurrent_flow_count,
         "note": "并发瓶颈场景的 flow 数量"},
        {"metric": "concurrent_flow_throughput_mbps", "value": round(concurrent_tp, 4),
         "note": "并发场景下每个 flow 平均吞吐量（Mbps）"},
        {"metric": "concurrent_flow_duration_s", "value": round(concurrent_duration, 4),
         "note": "3 条 30M 并发 flow 的平均传输耗时（秒）"},
        {"metric": "scaling_factor", "value": round(scaling_factor, 4),
         "note": "同大小 flow 下，并发相对单流的延迟放大倍数"},
        {"metric": "bottleneck_bandwidth_mbps", "value": round(bottleneck_bandwidth, 4),
         "note": "共享瓶颈链路标称带宽（Mbps）"},
        {"metric": "bottleneck_share_per_flow_mbps", "value": round(bottleneck_share, 4),
         "note": "理想公平共享下每个 flow 应分到的带宽"},
        {"metric": "fair_share_utilization_ratio", "value": round(fair_share_utilization, 4),
         "note": "并发实际吞吐 / 公平份额，越接近 1 越接近理想公平共享"},
        {"metric": "concurrent_throughput_std", "value": round(throughput_std, 4),
         "note": "3 个并发 flow 的吞吐量标准差（越小越公平）"},
        {"metric": "all_flows_share_bottleneck", "value": bool(all_same_bottleneck),
         "note": "所有 flow 是否走同一 bottleneck 链路"},
    ])


def data_self_check(
    flow_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    bottleneck_df: pd.DataFrame,
    paper_df: pd.DataFrame,
) -> Dict[str, bool]:
    """
    network_flow 样例的数据自洽检查（沿用 02/03 的 self_check 模式）。

    不变量：
    1. single_flow flow_count == 1
    2. concurrent_bottleneck flow_count == 3
    3. 单流 throughput 接近瓶颈带宽（≈10Mbps，>8Mbps）
    4. 并发每个流 throughput 接近 bottleneck/3（≈3.3Mbps，>2.5Mbps）
    5. scaling_factor 接近 3（3 条同大小 flow 公平共享同一瓶颈）
    6. 所有 flow 走同一 bottleneck（== 1 个 distinct bottleneck_link）
    7. total_bytes 单流 == 30M，并发 == 90M（3 × 30M）
    8. rtt_ms 一致（同一条路径，== 80ms）
    9. summary scaling_factor == paper scaling_factor
    10. bottleneck_summary 与 summary 自洽

    参数直接传进来（不要 dfs.get），避免 export_outputs 末尾才 set 的时序 bug。
    """
    if flow_df.empty:
        return {f"0{i+1}_xxx": False for i in range(10)}

    single_df = flow_df[flow_df["scenario"] == "single_flow"]
    concurrent_df = flow_df[flow_df["scenario"] == "concurrent_bottleneck"]

    single_count = len(single_df)
    concurrent_count = len(concurrent_df)

    # 吞吐量
    enriched = _enrich_flow_df(flow_df)
    single_tp = float(enriched[enriched["scenario"] == "single_flow"]["throughput_mbps"].mean()) \
        if single_count > 0 else 0.0
    concurrent_tp = float(enriched[enriched["scenario"] == "concurrent_bottleneck"]["throughput_mbps"].mean()) \
        if concurrent_count > 0 else 0.0

    # scaling_factor
    single_duration = float(single_df["duration"].mean()) if single_count > 0 else 0.0
    concurrent_duration = float(concurrent_df["duration"].mean()) if concurrent_count > 0 else 0.0
    scaling = concurrent_duration / single_duration if single_duration > 0 else 0.0

    # bottleneck 一致性
    distinct_bottlenecks = int(flow_df["bottleneck_link"].nunique()) if "bottleneck_link" in flow_df.columns else 0

    # bytes
    single_bytes = int(single_df["bytes"].sum()) if single_count > 0 else 0
    concurrent_bytes = int(concurrent_df["bytes"].sum()) if concurrent_count > 0 else 0

    # rtt_ms 一致性
    distinct_rtt = int(flow_df["rtt_ms"].nunique()) if "rtt_ms" in flow_df.columns else 99

    # paper_highlight 与 summary 自洽（容差 1e-3，因为 paper_highlight 的 value 做了 round 4 位）
    summary_scaling = None
    if not summary_df.empty and "scaling_factor" in summary_df.columns:
        concurrent_row = summary_df[summary_df["scenario"] == "concurrent_bottleneck"]
        if not concurrent_row.empty:
            summary_scaling = float(concurrent_row["scaling_factor"].iloc[0])
    paper_scaling = float(paper_df[paper_df["metric"] == "scaling_factor"]["value"].iloc[0]) \
        if not paper_df.empty and "scaling_factor" in paper_df["metric"].values else 0.0
    scaling_match = (summary_scaling is not None and abs(summary_scaling - paper_scaling) < 1e-3) \
        or (summary_scaling is None and abs(scaling - paper_scaling) < 1e-3)

    checks = {
        "01_single_flow_count_is_1": single_count == 1,
        "02_concurrent_flow_count_is_3": concurrent_count == 3,
        "03_single_throughput_near_bottleneck": single_tp > 8.0,
        "04_concurrent_throughput_near_share": concurrent_tp > 2.5,
        "05_scaling_factor_near_3": 2.7 <= scaling <= 3.3,
        "06_all_flows_share_one_bottleneck": distinct_bottlenecks == 1,
        "07_single_total_bytes_is_30M": abs(single_bytes - 30_000_000) < 1,
        "08_concurrent_total_bytes_is_90M": abs(concurrent_bytes - 90_000_000) < 1,
        "09_rtt_consistent_across_flows": distinct_rtt == 1,
        "10_summary_paper_scaling_consistent": bool(scaling_match),
    }

    return checks


def export_outputs(
    output_dir: Path,
    flow_records: List[Dict[str, Any]],
    route_records: List[Dict[str, Any]],
) -> Dict[str, pd.DataFrame]:
    """
    导出 network_flow 样例结果。

    输出：
    - network_flow.csv：每次网络流传输的原始记录
    - network_route.csv：静态路由信息
    - network_flow_performance.csv：每个 flow 的完整性能（论文 demo 关键图）
    - network_flow_summary.csv：增强版摘要（含 throughput_mbps / scaling_factor）
    - network_bottleneck_summary.csv：按 bottleneck 链路分组
    - network_flow_paper_highlight.csv：论文 demo 关键摘要（11 条 metric/value）
    - network_flow_self_check.csv：10 项数据自检
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    flow_df = pd.DataFrame(flow_records)
    route_df = pd.DataFrame(route_records)

    # 每个 flow 的完整性能（论文 demo 关键图）
    flow_perf_df = build_flow_performance(flow_df)

    # 增强版 summary
    summary_df = build_summary(flow_df)

    # 增强版 bottleneck summary
    bottleneck_summary_df = build_bottleneck_summary(flow_df)

    # 论文 demo 关键摘要
    paper_df = build_paper_highlight(
        flow_df=flow_df,
        summary_df=summary_df,
        bottleneck_df=bottleneck_summary_df,
    )
    paper_path = output_dir / "network_flow_paper_highlight.csv"
    paper_df.to_csv(paper_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_path)

    # 数据自检
    checks = data_self_check(
        flow_df=flow_df,
        summary_df=summary_df,
        bottleneck_df=bottleneck_summary_df,
        paper_df=paper_df,
    )
    check_df = pd.DataFrame([
        {"check_id": k, "passed": v} for k, v in checks.items()
    ])
    check_path = output_dir / "network_flow_self_check.csv"
    check_df.to_csv(check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", check_path)

    outputs = {
        "network_flow": flow_df,
        "network_route": route_df,
        "network_flow_performance": flow_perf_df,
        "network_flow_summary": summary_df,
        "network_bottleneck_summary": bottleneck_summary_df,
        "network_flow_paper_highlight": paper_df,
        "network_flow_self_check": check_df,
    }

    for name, df in outputs.items():
        if name in ("network_flow_paper_highlight", "network_flow_self_check"):
            continue  # 已单独保存
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
