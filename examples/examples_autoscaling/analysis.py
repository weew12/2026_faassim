"""
文件作用：自动伸缩样例的指标导出与简要分析工具。

main.py 在仿真结束后调用本文件中的函数，将 faas-sim 内部 metrics
导出为 CSV，并生成自动伸缩摘要，便于后续画图和论文分析。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "scale",
    "schedule",
    "function_deployment",
    "replica_deployment",
    "invocations",
    "flow",
]


def extract_metrics(sim) -> Dict[str, pd.DataFrame]:
    """
    从仿真对象中提取常用指标。

    参数：
    - sim：已经执行完成的 Simulation 对象。

    返回：
    - Dict[str, DataFrame]：指标名称到 DataFrame 的映射。
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


def build_replica_timeline(scale_df: pd.DataFrame) -> pd.DataFrame:
    """
    根据 scale 指标构造副本数量时间线。

    参数：
    - scale_df：faas-sim scale 指标 DataFrame。

    返回：
    - DataFrame：整理后的副本伸缩时间线。

    说明：
    不同版本 faas-sim 的 scale 指标字段可能略有不同，因此这里做宽松处理。
    只要字段存在，就尽量保留，避免因为字段差异导致样例失败。
    """
    if scale_df.empty:
        return pd.DataFrame()

    timeline_df = scale_df.reset_index()

    preferred_columns = [
        "time",
        "function_name",
        "replicas",
        "old_replicas",
        "new_replicas",
        "scale",
        "value",
        "reason",
    ]

    existing_columns = [col for col in preferred_columns if col in timeline_df.columns]

    if not existing_columns:
        return timeline_df

    return timeline_df[existing_columns]


def build_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成自动伸缩样例摘要。

    摘要内容包括：
    - scale 指标行数；
    - invocation 指标行数；
    - schedule 指标行数；
    - 副本部署指标行数；
    - 平均执行时间。
    """
    scale_df = dfs.get("scale", pd.DataFrame())
    invocations_df = dfs.get("invocations", pd.DataFrame())
    schedule_df = dfs.get("schedule", pd.DataFrame())
    replica_deployment_df = dfs.get("replica_deployment", pd.DataFrame())

    avg_exec_time = None
    if not invocations_df.empty and "t_exec" in invocations_df.columns:
        avg_exec_time = float(invocations_df["t_exec"].mean())

    summary = {
        "scale_events": len(scale_df),
        "invocation_events": len(invocations_df),
        "schedule_events": len(schedule_df),
        "replica_deployment_events": len(replica_deployment_df),
        "avg_exec_time": avg_exec_time,
    }

    return pd.DataFrame([summary])


def export_outputs(sim, output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。

    参数：
    - sim：已经运行完成的 Simulation 对象；
    - output_dir：输出目录。

    返回：
    - Dict[str, DataFrame]：导出的指标表。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    timeline_df = build_replica_timeline(dfs.get("scale", pd.DataFrame()))
    timeline_path = output_dir / "autoscaling_replica_timeline.csv"
    timeline_df.to_csv(timeline_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", timeline_path)

    summary_df = build_summary(dfs)
    summary_path = output_dir / "autoscaling_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", summary_path)

    dfs["autoscaling_replica_timeline"] = timeline_df
    dfs["autoscaling_summary"] = summary_df

    return dfs
