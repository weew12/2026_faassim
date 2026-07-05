"""
文件作用：cosimulation 样例的指标导出与分析工具。

该文件负责导出外部 trace、控制交换记录、阶段切换记录、函数调用探针和 faas-sim 常规指标，
并生成协同仿真摘要。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


METRIC_NAMES = [
    "cosim_exchange",
    "cosim_phase",
    "cosim_invoke_probe",
    "invocations",
    "schedule",
    "function_deployments",
    "function_deployment_lifecycle",
    "function_replicas",
    "replica_deployment",
    "flow",
    "resource",
    "resources",
    "resource_monitor",
    "resource_state",
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


def build_phase_invoke_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    按外部阶段汇总函数调用耗时。
    """
    invoke_df = dfs.get("cosim_invoke_probe", pd.DataFrame())

    if invoke_df.empty:
        return pd.DataFrame([{
            "invoke_events": 0,
        }])

    if "phase_name" not in invoke_df.columns or "final_duration" not in invoke_df.columns:
        return pd.DataFrame([{
            "invoke_events": len(invoke_df),
            "columns": ",".join(invoke_df.columns.astype(str).tolist()),
        }])

    return (
        invoke_df
        .groupby(["phase_name", "controller_action"])
        .agg(
            invoke_events=("final_duration", "count"),
            avg_final_duration=("final_duration", "mean"),
            max_final_duration=("final_duration", "max"),
            avg_runtime_factor=("runtime_factor", "mean"),
            avg_network_delay=("network_delay", "mean"),
        )
        .reset_index()
    )


def build_exchange_summary(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    汇总外部控制器与 faas-sim 之间的交换记录。
    """
    exchange_df = dfs.get("cosim_exchange", pd.DataFrame())

    if exchange_df.empty:
        return pd.DataFrame([{
            "exchange_events": 0,
        }])

    if "phase_name" not in exchange_df.columns:
        return pd.DataFrame([{
            "exchange_events": len(exchange_df),
            "columns": ",".join(exchange_df.columns.astype(str).tolist()),
        }])

    return (
        exchange_df
        .groupby(["phase_name", "controller_action"])
        .agg(
            exchange_events=("runtime_factor", "count"),
            avg_runtime_factor=("runtime_factor", "mean"),
            avg_network_delay=("network_delay", "mean"),
            avg_observed_active_requests=("observed_active_requests", "mean"),
        )
        .reset_index()
    )


def export_outputs(sim, output_dir: Path, external_trace) -> Dict[str, pd.DataFrame]:
    """
    导出协同仿真结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    dfs = extract_metrics(sim)

    for name, df in dfs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, encoding="utf-8-sig")
        logger.info("saved %s", path)

    trace_df = external_trace.to_dataframe()
    trace_path = output_dir / "external_environment_trace.csv"
    trace_df.to_csv(trace_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_path)

    phase_invoke_summary_df = build_phase_invoke_summary(dfs)
    phase_invoke_summary_path = output_dir / "cosim_phase_invoke_summary.csv"
    phase_invoke_summary_df.to_csv(phase_invoke_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", phase_invoke_summary_path)

    exchange_summary_df = build_exchange_summary(dfs)
    exchange_summary_path = output_dir / "cosim_exchange_summary.csv"
    exchange_summary_df.to_csv(exchange_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", exchange_summary_path)

    dfs["external_environment_trace"] = trace_df
    dfs["cosim_phase_invoke_summary"] = phase_invoke_summary_df
    dfs["cosim_exchange_summary"] = exchange_summary_df

    return dfs
