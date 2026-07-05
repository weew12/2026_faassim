"""
文件作用：Skippy 调度样例的指标导出与简要分析工具。

该文件负责从 sim.env.metrics 中提取调度相关 DataFrame，并保存到 outputs/ 目录。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "skippy_scheduler_result",
    "skippy_scheduler_candidate",
    "schedule",
    "allocation",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "invocations",
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


def build_scheduler_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成 Skippy 调度摘要。
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    candidate_df = dfs.get("skippy_scheduler_candidate", pd.DataFrame())

    if result_df.empty:
        return pd.DataFrame([{
            "schedule_result_events": 0,
            "schedule_metric_events": len(schedule_df),
            "candidate_snapshot_events": len(candidate_df),
            "selected_node_count": 0,
            "avg_feasible_nodes_full": None,
        }])

    selected_node_count = result_df["selected_node"].nunique() if "selected_node" in result_df.columns else None
    avg_feasible_nodes = (
        float(result_df["feasible_nodes_full"].mean())
        if "feasible_nodes_full" in result_df.columns
        else None
    )

    return pd.DataFrame([{
        "schedule_result_events": len(result_df),
        "schedule_metric_events": len(schedule_df),
        "candidate_snapshot_events": len(candidate_df),
        "selected_node_count": selected_node_count,
        "avg_feasible_nodes_full": avg_feasible_nodes,
    }])


def build_selected_node_distribution(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    统计调度结果中目标节点的分布。
    """
    result_df = dfs.get("skippy_scheduler_result", pd.DataFrame())

    if result_df.empty or "selected_node" not in result_df.columns:
        return pd.DataFrame()

    group_columns = [
        col for col in [
            "selected_node",
            "needed_images",
        ]
        if col in result_df.columns
    ]

    return (
        result_df
        .groupby(group_columns)
        .size()
        .reset_index(name="scheduled_pods")
        .sort_values("scheduled_pods", ascending=False)
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

    summary_df = build_scheduler_summary(dfs)
    summary_path = output_dir / "skippy_scheduler_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    selected_node_df = build_selected_node_distribution(dfs)
    selected_node_path = output_dir / "skippy_selected_node_distribution.csv"
    selected_node_df.to_csv(selected_node_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", selected_node_path)

    dfs["skippy_scheduler_summary"] = summary_df
    dfs["skippy_selected_node_distribution"] = selected_node_df

    return dfs
