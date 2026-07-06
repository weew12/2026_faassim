"""
文件作用：负载均衡样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成负载均衡摘要，便于观察请求是否均匀分配到多个副本。

新增的关键导出：
- load_balancer_routing_sequence.csv：每次路由的 request_id -> replica_index
  序列，这是论文 demo 的关键图（"轮询路由的严格顺序"）。
- load_balancer_summary.csv：增强版，加 max/min/balance_std/balance_ratio 等
  均衡度指标。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "load_balancer",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
]


def extract_metrics(sim) -> Dict[str, pd.DataFrame]:
    """
    从仿真对象中提取常用指标。
    """
    dfs: Dict[str, pd.DataFrame] = {}
    for name in METRIC_NAMES:
        try:
            df = sim.env.metrics.extract_dataframe(name)
            dfs[name] = df
            logger.info("metric %s extracted, rows=%d", name, len(df))
        except Exception as err:
            logger.warning("metric %s not available: %s", name, err)
            dfs[name] = pd.DataFrame()
    return dfs


def build_load_balancer_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成增强版负载均衡摘要。

    摘要字段（按论文 demo 关心维度排序）：
    - route_events / invocation_events
    - selected_replica_count / selected_node_count
    - max_routed_requests / min_routed_requests（每个 replica 的请求数）
    - balance_std（请求数标准差，越小越均衡）
    - balance_ratio（min/max，越接近 1 越均衡）
    - max_consecutive_same_replica（轮询中同一 replica 连续出现的最大次数，
      用于检查 LB 公平性，对严格轮询应该是 1）
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if lb_df.empty:
        return pd.DataFrame([{
            "route_events": 0,
            "invocation_events": len(invocations_df),
            "selected_replica_count": 0,
            "selected_node_count": 0,
            "max_routed_requests": 0,
            "min_routed_requests": 0,
            "balance_std": None,
            "balance_ratio": None,
            "max_consecutive_same_replica": None,
        }])

    selected_replica_count = lb_df["selected_replica_id"].nunique() if "selected_replica_id" in lb_df.columns else None
    selected_node_count = lb_df["selected_node"].nunique() if "selected_node" in lb_df.columns else None

    # 均衡度统计：先按 replica 分组求 count
    if "selected_replica_id" in lb_df.columns:
        per_replica = lb_df.groupby("selected_replica_id").size()
        max_routed = int(per_replica.max())
        min_routed = int(per_replica.min())
        balance_std = float(per_replica.std(ddof=0))  # 总体标准差
        balance_ratio = float(min_routed / max_routed) if max_routed > 0 else None
    else:
        max_routed = None
        min_routed = None
        balance_std = None
        balance_ratio = None

    # 同一 replica 连续出现的最大次数（对严格轮询应该是 1）
    max_consecutive = None
    if "request_id" in lb_df.columns and "selected_replica_id" in lb_df.columns:
        sorted_df = lb_df.sort_values("request_id")
        prev = None
        per_replica_consec = {}  # 每个 replica 的最大连续次数
        per_replica_cur = {}    # 当前连续计数（遇不同 replica 时必须重置为 1）
        for _, row in sorted_df.iterrows():
            rid = row["selected_replica_id"]
            if prev is not None and rid == prev:
                # 同一 replica 连续出现
                per_replica_cur[rid] = per_replica_cur.get(rid, 0) + 1
            else:
                # 不同 replica，重置为 1
                per_replica_cur[rid] = 1
            per_replica_consec[rid] = max(per_replica_consec.get(rid, 0), per_replica_cur[rid])
            prev = rid
        max_consecutive = max(per_replica_consec.values()) if per_replica_consec else None

    return pd.DataFrame([{
        "route_events": len(lb_df),
        "invocation_events": len(invocations_df),
        "selected_replica_count": selected_replica_count,
        "selected_node_count": selected_node_count,
        "max_routed_requests": max_routed,
        "min_routed_requests": min_routed,
        "balance_std": balance_std,
        "balance_ratio": balance_ratio,
        "max_consecutive_same_replica": max_consecutive,
    }])


def build_replica_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计请求在各副本之间的分布。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())

    if lb_df.empty or "selected_replica_id" not in lb_df.columns:
        return pd.DataFrame()

    group_columns = [
        col for col in [
            "function_name",
            "selected_node",
            "selected_image",
            "selected_replica_id",
            "policy",
        ]
        if col in lb_df.columns
    ]

    return (
        lb_df
        .groupby(group_columns)
        .size()
        .reset_index(name="routed_requests")
        .sort_values("routed_requests", ascending=False)
    )


def build_routing_sequence(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成论文 demo 关键的"轮询路由序列"。

    返回 DataFrame 列：[request_id, replica_index, selected_replica_id, selected_node]
    按 request_id 升序排序。这是最直接的 "x=request_id, y=replica_index" 阶梯图数据。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())

    if lb_df.empty or "request_id" not in lb_df.columns:
        return pd.DataFrame()

    preferred = [
        "request_id",
        "replica_index",
        "selected_replica_id",
        "selected_node",
    ]
    existing = [c for c in preferred if c in lb_df.columns]

    if not existing:
        return pd.DataFrame()

    return (
        lb_df[existing]
        .sort_values("request_id")
        .reset_index(drop=True)
    )


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    输出：
    - 8 个 faas-sim 内置 metric 的 CSV
    - load_balancer_routing_sequence.csv：路由序列（论文 demo 关键）
    - load_balancer_summary.csv：增强版摘要
    - load_balancer_replica_distribution.csv：副本分布
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    # 新增：轮询路由序列（论文 demo 关键图）
    routing_seq_df = build_routing_sequence(dfs)
    routing_seq_path = output_dir / "load_balancer_routing_sequence.csv"
    routing_seq_df.to_csv(routing_seq_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", routing_seq_path)

    summary_df = build_load_balancer_summary(dfs)
    summary_path = output_dir / "load_balancer_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    distribution_df = build_replica_distribution(dfs)
    distribution_path = output_dir / "load_balancer_replica_distribution.csv"
    distribution_df.to_csv(distribution_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", distribution_path)

    dfs["load_balancer_routing_sequence"] = routing_seq_df
    dfs["load_balancer_summary"] = summary_df
    dfs["load_balancer_replica_distribution"] = distribution_df

    return dfs
