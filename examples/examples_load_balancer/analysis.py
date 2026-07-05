"""
文件作用：负载均衡样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成负载均衡摘要，便于观察请求是否均匀分配到多个副本。
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
    生成负载均衡摘要。

    摘要主要统计每个副本被选中的次数，以及每个节点承载的请求数量。
    """
    lb_df = dfs.get("load_balancer", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if lb_df.empty:
        return pd.DataFrame([{
            "route_events": 0,
            "invocation_events": len(invocations_df),
            "selected_replica_count": 0,
            "selected_node_count": 0,
        }])

    selected_replica_count = lb_df["selected_replica_id"].nunique() if "selected_replica_id" in lb_df.columns else None
    selected_node_count = lb_df["selected_node"].nunique() if "selected_node" in lb_df.columns else None

    return pd.DataFrame([{
        "route_events": len(lb_df),
        "invocation_events": len(invocations_df),
        "selected_replica_count": selected_replica_count,
        "selected_node_count": selected_node_count,
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


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    summary_df = build_load_balancer_summary(dfs)
    summary_path = output_dir / "load_balancer_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    distribution_df = build_replica_distribution(dfs)
    distribution_path = output_dir / "load_balancer_replica_distribution.csv"
    distribution_df.to_csv(distribution_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", distribution_path)

    dfs["load_balancer_summary"] = summary_df
    dfs["load_balancer_replica_distribution"] = distribution_df

    return dfs
