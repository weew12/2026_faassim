"""
文件作用：trace_oracle 样例的指标导出与简要分析工具。

该文件负责导出 trace_oracle_sample、invocations、schedule 等指标，
并生成 trace-driven 执行时间摘要。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

from oracle import TraceRuntimeOracle

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "trace_oracle_sample",
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


def build_trace_sample_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据实际取样记录生成执行时间摘要。
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame())

    if sample_df.empty:
        return pd.DataFrame([{
            "sample_events": 0,
        }])

    group_columns = [
        col for col in ["function_name"]
        if col in sample_df.columns
    ]

    if not group_columns or "duration" not in sample_df.columns:
        return pd.DataFrame([{
            "sample_events": len(sample_df),
            "columns": ",".join(sample_df.columns.astype(str).tolist()),
        }])

    return (
        sample_df
        .groupby(group_columns)
        .agg(
            sample_events=("duration", "count"),
            avg_sampled_duration=("duration", "mean"),
            min_sampled_duration=("duration", "min"),
            max_sampled_duration=("duration", "max"),
        )
        .reset_index()
    )


def build_invocation_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    根据 invocations 指标生成调用摘要。
    """
    invocations_df = dfs.get("invocations", pd.DataFrame())

    if invocations_df.empty:
        return pd.DataFrame([{
            "invocation_events": 0,
        }])

    if "function_name" not in invocations_df.columns:
        return pd.DataFrame([{
            "invocation_events": len(invocations_df),
            "columns": ",".join(invocations_df.columns.astype(str).tolist()),
        }])

    agg_dict = {
        "invocation_events": ("function_name", "count"),
    }

    if "duration" in invocations_df.columns:
        agg_dict["avg_invocation_duration"] = ("duration", "mean")
        agg_dict["max_invocation_duration"] = ("duration", "max")

    return (
        invocations_df
        .groupby("function_name")
        .agg(**agg_dict)
        .reset_index()
    )


def export_outputs(sim, output_dir: Path, trace_path: Path) -> Dict[str, pd.DataFrame]:
    """
    导出仿真输出指标。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    trace_oracle = TraceRuntimeOracle(trace_path)
    trace_input_summary_df = trace_oracle.summary_dataframe()
    trace_input_summary_path = output_dir / "trace_input_summary.csv"
    trace_input_summary_df.to_csv(trace_input_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_input_summary_path)

    trace_sample_summary_df = build_trace_sample_summary(dfs)
    trace_sample_summary_path = output_dir / "trace_sample_summary.csv"
    trace_sample_summary_df.to_csv(trace_sample_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_sample_summary_path)

    invocation_summary_df = build_invocation_summary(dfs)
    invocation_summary_path = output_dir / "trace_invocation_summary.csv"
    invocation_summary_df.to_csv(invocation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invocation_summary_path)

    dfs["trace_input_summary"] = trace_input_summary_df
    dfs["trace_sample_summary"] = trace_sample_summary_df
    dfs["trace_invocation_summary"] = invocation_summary_df

    return dfs
