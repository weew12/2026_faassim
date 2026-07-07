"""
文件作用：trace_oracle 样例的指标导出与简要分析工具。

该文件负责导出 trace_oracle_sample、invocations、schedule 等指标，
并生成 trace-driven 执行时间摘要。

新增的关键导出：
- trace_invoke_sample_join.csv：每个 invoke 与其使用的 trace sample 一一对应，
  论文 demo 关键证据：证明 oracle 取样和 invoke 实际执行时间完全一致。
- trace_cycle_summary.csv：trace 循环覆盖证据。
  fast 函数 16 次 invoke 但 trace 只有 12 个样本，cursor 会循环回 sample_id=1。
  slow 函数 12 次 invoke 恰好覆盖一个完整 cycle，不循环。
"""

import logging
from pathlib import Path
from typing import Dict, List

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


def build_trace_invoke_sample_join(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    把 trace_oracle_sample 与 invocations 按 (function_name, 取样次序) 一一对应。

    trace_oracle_sample 按记录顺序记录了 oracle 实际派出的样本；
    invocations 按 t_start 顺序记录了每次函数调用。
    对同一函数，把两者按各自的出现顺序对齐，就得到：

    - sample_id         trace 中本次 invoke 使用的样本序号
    - sample_duration   oracle 派出的执行时间（来自 trace）
    - inv_t_exec        invocations.csv 中本次 invoke 的实际执行时间
    - duration_match    sample_duration 和 inv_t_exec 是否完全相等

    论文 demo 关键证据：证明 oracle 取样和实际 invoke 执行时间一致。
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame()).copy()
    inv_df = dfs.get("invocations", pd.DataFrame()).copy()

    if sample_df.empty or inv_df.empty:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "missing trace_oracle_sample or invocations dataframe",
        }])

    if "function_name" not in sample_df.columns or "function_name" not in inv_df.columns:
        return pd.DataFrame([{
            "join_rows": 0,
            "message": "function_name column missing",
        }])

    if "t_exec" in inv_df.columns:
        inv_df["t_exec"] = pd.to_numeric(inv_df["t_exec"], errors="coerce")
    if "t_start" in inv_df.columns:
        inv_df["t_start"] = pd.to_numeric(inv_df["t_start"], errors="coerce")

    # 按函数分别按记录顺序对齐。
    rows: List[dict] = []
    for fn in sorted(set(sample_df["function_name"].unique()) | set(inv_df["function_name"].unique())):
        samp_fn = sample_df[sample_df["function_name"] == fn].sort_index().reset_index(drop=True)
        inv_fn = inv_df[inv_df["function_name"] == fn].sort_values("t_start").reset_index(drop=True)

        n = min(len(samp_fn), len(inv_fn))
        for i in range(n):
            s = samp_fn.iloc[i]
            inv = inv_fn.iloc[i]
            duration_match = (
                pd.notna(inv["t_exec"])
                and abs(float(s["duration"]) - float(inv["t_exec"])) < 1e-6
            )
            rows.append({
                "function_name": fn,
                "invoke_order": i + 1,
                "sample_id": int(s["sample_id"]),
                "sample_duration": float(s["duration"]),
                "request_id": s.get("request_id") if "request_id" in s else None,
                "node": s.get("node_name") if "node_name" in s else None,
                "inv_t_start": float(inv["t_start"]) if pd.notna(inv["t_start"]) else None,
                "inv_t_exec": float(inv["t_exec"]) if pd.notna(inv["t_exec"]) else None,
                "inv_t_wait": float(inv["t_wait"]) if pd.notna(inv["t_wait"]) else None,
                "duration_match": duration_match,
            })

    return pd.DataFrame(rows)


def build_trace_cycle_summary(
    dfs: Dict[str, pd.DataFrame],
    trace_input_summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    统计每个函数的 trace 循环覆盖情况。

    - input_samples：trace CSV 中的样本数
    - actual_samples：本次 run 实际取样次数（来自 trace_oracle_sample）
    - cycles_used：actual_samples / input_samples 向上取整
      例如 fast 函数 16 次 invoke、12 个 trace 样本 → cycles_used=2
    - cycles_used_minus_first：完整 cycle 数（不含最后一个不完整 cycle）
    - last_sample_id：最后一次取样的 sample_id（用于验证循环回卷行为）
    """
    sample_df = dfs.get("trace_oracle_sample", pd.DataFrame()).copy()

    if sample_df.empty or trace_input_summary.empty:
        return pd.DataFrame([{
            "trace_cycle_rows": 0,
            "message": "missing trace_oracle_sample or trace_input_summary",
        }])

    rows: List[dict] = []
    for fn in trace_input_summary["function_name"].tolist():
        input_count = int(
            trace_input_summary.loc[
                trace_input_summary["function_name"] == fn, "sample_count"
            ].iloc[0]
        )
        sub = sample_df[sample_df["function_name"] == fn].sort_index()
        actual = len(sub)
        cycles = (actual + input_count - 1) // input_count if input_count > 0 else 0
        full_cycles = actual // input_count if input_count > 0 else 0
        last_sample_id = int(sub["sample_id"].iloc[-1]) if not sub.empty else None
        rows.append({
            "function_name": fn,
            "input_samples": input_count,
            "actual_samples": actual,
            "cycles_used": cycles,
            "full_cycles": full_cycles,
            "last_sample_id": last_sample_id,
        })

    return pd.DataFrame(rows)


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

    trace_join_df = build_trace_invoke_sample_join(dfs)
    trace_join_path = output_dir / "trace_invoke_sample_join.csv"
    trace_join_df.to_csv(trace_join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_join_path)

    trace_cycle_df = build_trace_cycle_summary(dfs, trace_input_summary_df)
    trace_cycle_path = output_dir / "trace_cycle_summary.csv"
    trace_cycle_df.to_csv(trace_cycle_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", trace_cycle_path)

    invocation_summary_df = build_invocation_summary(dfs)
    invocation_summary_path = output_dir / "trace_invocation_summary.csv"
    invocation_summary_df.to_csv(invocation_summary_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", invocation_summary_path)

    dfs["trace_input_summary"] = trace_input_summary_df
    dfs["trace_sample_summary"] = trace_sample_summary_df
    dfs["trace_invoke_sample_join"] = trace_join_df
    dfs["trace_cycle_summary"] = trace_cycle_df
    dfs["trace_invocation_summary"] = invocation_summary_df

    return dfs