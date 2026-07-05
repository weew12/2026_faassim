"""
文件作用：批量结果聚合与策略对比。

该文件负责把 run-level 结果进一步聚合为 policy / workload 级别摘要，
并生成同一 workload 下不同策略之间的对比表。
"""

import pandas as pd


def aggregate_by_policy_workload(run_metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    按 policy / workload 聚合实验结果。
    """
    if run_metrics_df.empty:
        return pd.DataFrame()

    agg_spec = {
        "runs": ("run_id", "count"),
        "avg_probe_events": ("probe_events", "mean"),
        "avg_invocation_events": ("invocation_events", "mean"),
    }

    optional_metrics = [
        ("probe_avg_duration", "mean_probe_avg_duration"),
        ("probe_p95_duration", "mean_probe_p95_duration"),
        ("invocation_avg_duration", "mean_invocation_avg_duration"),
        ("flow_total_bytes", "mean_flow_total_bytes"),
        ("scheduled_node_count", "mean_scheduled_node_count"),
    ]

    for source_col, target_col in optional_metrics:
        if source_col in run_metrics_df.columns:
            agg_spec[target_col] = (source_col, "mean")

    return (
        run_metrics_df
        .groupby(["policy", "workload"])
        .agg(**agg_spec)
        .reset_index()
    )


def build_policy_comparison(
    summary_df: pd.DataFrame,
    baseline_policy: str = "default_skippy",
) -> pd.DataFrame:
    """
    构造策略对比表。

    对每个 workload，以 baseline_policy 为基线，计算其他策略在关键指标上的相对变化。
    """
    if summary_df.empty or "policy" not in summary_df.columns or "workload" not in summary_df.columns:
        return pd.DataFrame()

    rows = []

    for workload, group in summary_df.groupby("workload"):
        baseline_rows = group[group["policy"] == baseline_policy]
        if baseline_rows.empty:
            continue

        baseline = baseline_rows.iloc[0]

        for _, row in group.iterrows():
            policy = row["policy"]

            item = {
                "workload": workload,
                "baseline_policy": baseline_policy,
                "policy": policy,
            }

            for metric in [
                "mean_probe_avg_duration",
                "mean_probe_p95_duration",
                "mean_invocation_avg_duration",
                "mean_flow_total_bytes",
            ]:
                if metric in group.columns:
                    base_value = baseline.get(metric)
                    current_value = row.get(metric)
                    item[f"{metric}_baseline"] = base_value
                    item[f"{metric}_current"] = current_value
                    item[f"{metric}_delta"] = safe_delta(current_value, base_value)
                    item[f"{metric}_relative"] = safe_relative_delta(current_value, base_value)

            rows.append(item)

    return pd.DataFrame(rows)


def safe_delta(current, baseline):
    """
    安全计算差值。
    """
    try:
        return float(current) - float(baseline)
    except Exception:
        return None


def safe_relative_delta(current, baseline):
    """
    安全计算相对变化。
    """
    try:
        baseline = float(baseline)
        current = float(current)
        if baseline == 0:
            return None
        return (current - baseline) / baseline
    except Exception:
        return None
