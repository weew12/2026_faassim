"""
文件作用：论文实验结果导出与分析。
"""

import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def build_policy_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成策略级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())
    evict_df = outputs.get("thesis_eviction_event", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    summary = (
        df
        .groupby(["case_id", "policy_name"])
        .agg(
            request_count=("request_id", "count"),
            warm_hits=("warm_hit", "sum"),
            image_cache_hits=("image_cache_hit", "sum"),
            data_cache_hits=("data_cache_hit", "sum"),
            avg_latency=("latency", "mean"),
            p95_latency=("latency", lambda s: float(s.quantile(0.95))),
            total_latency=("latency", "sum"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            total_image_pull_penalty=("image_pull_penalty", "sum"),
            total_data_fetch_penalty=("data_fetch_penalty", "sum"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            avg_cache_used=("cache_used_after", "mean"),
        )
        .reset_index()
        .assign(
            warm_hit_rate=lambda x: x["warm_hits"] / x["request_count"],
            image_cache_hit_rate=lambda x: x["image_cache_hits"] / x["request_count"],
            data_cache_hit_rate=lambda x: x["data_cache_hits"] / x["request_count"],
        )
    )

    if not evict_df.empty:
        evict_summary = (
            evict_df
            .groupby(["case_id", "policy_name"])
            .agg(eviction_count=("evicted_function", "count"))
            .reset_index()
        )
        summary = summary.merge(evict_summary, on=["case_id", "policy_name"], how="left")
    else:
        summary["eviction_count"] = 0

    summary["eviction_count"] = summary["eviction_count"].fillna(0).astype(int)
    return summary


def build_function_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成函数级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "function_name"])
        .agg(
            request_count=("request_id", "count"),
            warm_hit_rate=("warm_hit", "mean"),
            avg_latency=("latency", "mean"),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
            avg_cache_utility=("cache_utility", "mean"),
            max_r_desired=("r_desired", "max"),
        )
        .reset_index()
    )


def build_phase_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成阶段级摘要。
    """
    df = outputs.get("thesis_request_result", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "phase"])
        .agg(
            request_count=("request_id", "count"),
            warm_hit_rate=("warm_hit", "mean"),
            avg_latency=("latency", "mean"),
            p95_latency=("latency", lambda s: float(s.quantile(0.95))),
            total_cold_start_penalty=("cold_start_penalty", "sum"),
        )
        .reset_index()
    )


def build_control_summary(outputs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成控制动作摘要。
    """
    df = outputs.get("thesis_control_decision", pd.DataFrame())

    if df.empty:
        return pd.DataFrame()

    return (
        df
        .groupby(["case_id", "policy_name", "action", "reason"])
        .agg(
            events=("request_id", "count"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            avg_cache_utility=("cache_utility", "mean"),
        )
        .reset_index()
    )


def build_baseline_comparison(policy_summary: pd.DataFrame) -> pd.DataFrame:
    """
    以 LoadOnly 为基线生成相对改进表。
    """
    if policy_summary.empty or "load_only" not in set(policy_summary["case_id"]):
        return pd.DataFrame()

    baseline = policy_summary[policy_summary["case_id"] == "load_only"].iloc[0]
    rows = []

    for row in policy_summary.itertuples(index=False):
        rows.append({
            "case_id": row.case_id,
            "policy_name": row.policy_name,
            "avg_latency": row.avg_latency,
            "avg_latency_change_vs_load_only": safe_ratio(baseline.avg_latency - row.avg_latency, baseline.avg_latency),
            "total_cold_start_penalty": row.total_cold_start_penalty,
            "cold_start_reduction_vs_load_only": safe_ratio(
                baseline.total_cold_start_penalty - row.total_cold_start_penalty,
                baseline.total_cold_start_penalty,
            ),
            "warm_hit_rate": row.warm_hit_rate,
            "warm_hit_rate_delta_vs_load_only": row.warm_hit_rate - baseline.warm_hit_rate,
        })

    return pd.DataFrame(rows)


def safe_ratio(numerator: float, denominator: float) -> float:
    """
    安全比例计算。
    """
    if abs(denominator) < 1e-9:
        return 0.0
    return numerator / denominator


def export_outputs(outputs: Dict[str, pd.DataFrame], output_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    导出全部实验结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = dict(outputs)
    outputs["thesis_policy_summary"] = build_policy_summary(outputs)
    outputs["thesis_function_summary"] = build_function_summary(outputs)
    outputs["thesis_phase_summary"] = build_phase_summary(outputs)
    outputs["thesis_control_summary"] = build_control_summary(outputs)
    outputs["thesis_baseline_comparison"] = build_baseline_comparison(outputs["thesis_policy_summary"])

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    write_report(outputs, output_dir / "thesis_experiment_report.md")
    return outputs


def write_report(outputs: Dict[str, pd.DataFrame], path: Path):
    """
    生成 Markdown 实验报告。
    """
    policy_summary = outputs.get("thesis_policy_summary", pd.DataFrame())
    comparison = outputs.get("thesis_baseline_comparison", pd.DataFrame())
    phase_summary = outputs.get("thesis_phase_summary", pd.DataFrame())

    lines = []
    lines.append("# Thesis Experiment Report")
    lines.append("")
    lines.append("## Policy Summary")
    lines.append("")
    lines.append(df_to_markdown(policy_summary))
    lines.append("")
    lines.append("## Comparison with LoadOnly")
    lines.append("")
    lines.append(df_to_markdown(comparison))
    lines.append("")
    lines.append("## Phase Summary")
    lines.append("")
    lines.append(df_to_markdown(phase_summary))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `R_cache` represents cache-driven warm replica demand.")
    lines.append("- `R_load` represents load-driven replica demand.")
    lines.append("- `CacheAwareJoint` combines both terms using `R_desired = max(R_cache, R_load)` and uses cache-aware node scoring.")
    lines.append("- This example is trace-driven and independent from faas-sim core APIs, so it is stable across local source versions.")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("saved %s", path)


def df_to_markdown(df: pd.DataFrame) -> str:
    """
    DataFrame 转 Markdown；缺失 tabulate 时回退为 CSV 文本。
    """
    if df is None or df.empty:
        return "_No data._"

    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```text\n" + df.to_csv(index=False) + "```"
