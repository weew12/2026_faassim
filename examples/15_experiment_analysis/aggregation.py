"""
文件作用：批量结果聚合与策略对比。

该文件负责把 run-level 结果进一步聚合为 policy / workload 级别摘要，
并生成同一 workload 下不同策略之间的对比表和论文 demo 关键摘要。
"""

from typing import Any, Dict, List

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
        ("invocation_p95_duration", "mean_invocation_p95_duration"),
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
    baseline 自身被跳过（避免生成 delta=0、relative=0 的无意义行）。
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

            # 跳过 baseline 自身：避免生成 delta=0、relative=0 的无意义行
            if policy == baseline_policy:
                continue

            item = {
                "workload": workload,
                "baseline_policy": baseline_policy,
                "policy": policy,
            }

            for metric in [
                "mean_probe_avg_duration",
                "mean_probe_p95_duration",
                "mean_invocation_avg_duration",
                "mean_invocation_p95_duration",
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


def build_paper_highlight(
    run_metrics_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    capacity_target_node: str = "server_1",
) -> pd.DataFrame:
    """
    论文 demo 关键摘要（与 14_batch_experiment 的 batch_paper_highlight 对应，
    沿用 02-13 的 metric/value/note 三列模式）。

    包含：
    - 跨 run 聚合 metric（total_runs / total_policies / total_workloads / total_seeds）
    - per-policy scheduled_nodes 列表
    - per-policy high_capacity_hit_ratio（scheduled_node == server_1 的比例）
    - per-workload policy 平均 probe duration 对比
    - per-workload policy speedup_ratio（fixed_node / default_skippy，>1 表示 baseline 更慢）
    - per-workload policy relative change 关键指标

    对比 14 的 batch_paper_highlight：15 多了 comparison_df（基于 baseline 的 relative
    change），便于论文里直接引用"fixed_node vs default_skippy 在 medium_load 的
    probe_avg_duration 上升 X%"。
    """
    if run_metrics_df.empty:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []

    # 0. 跨 run 聚合 metric
    rows.append({
        "metric": "total_runs",
        "value": int(len(run_metrics_df)),
        "note": "分析的 run 总数（每个 case 一行）",
    })
    if "policy" in run_metrics_df.columns:
        rows.append({
            "metric": "total_policies",
            "value": int(run_metrics_df["policy"].nunique()),
            "note": "策略数（聚合维度）",
        })
    if "workload" in run_metrics_df.columns:
        rows.append({
            "metric": "total_workloads",
            "value": int(run_metrics_df["workload"].nunique()),
            "note": "负载数（聚合维度）",
        })
    if "seed" in run_metrics_df.columns:
        rows.append({
            "metric": "total_seeds",
            "value": int(run_metrics_df["seed"].nunique()),
            "note": "随机种子数",
        })
    if "invocation_events" in run_metrics_df.columns:
        total_invocations = int(run_metrics_df["invocation_events"].sum())
        rows.append({
            "metric": "total_invocations",
            "value": total_invocations,
            "note": "跨所有 run 的总 invoke 次数",
        })
    if "probe_events" in run_metrics_df.columns:
        total_probes = int(run_metrics_df["probe_events"].sum())
        rows.append({
            "metric": "total_probes",
            "value": total_probes,
            "note": "跨所有 run 的总 probe 次数（应 == total_invocations）",
        })

    # comparison 行数（聚合指标）
    rows.append({
        "metric": "comparison_row_count",
        "value": int(len(comparison_df)) if not comparison_df.empty else 0,
        "note": "experiment_policy_comparison.csv 的行数（baseline 自身被跳过，应 == (policies-1) × workloads）",
    })

    # 1. 每 policy 实际选过的节点
    if "scheduled_node" in run_metrics_df.columns:
        for policy in sorted(run_metrics_df["policy"].dropna().unique()):
            sub = run_metrics_df[run_metrics_df.policy == policy]
            nodes = sorted(sub["scheduled_node"].dropna().astype(str).unique().tolist())
            rows.append({
                "metric": f"scheduled_nodes__{policy}",
                "value": ",".join(nodes),
                "note": f"{policy} 策略实际选过的节点集合（聚合自 {len(sub)} 个 run）",
            })
            total = len(sub)
            high = int((sub["scheduled_node"] == capacity_target_node).sum())
            ratio = (high / total) if total > 0 else 0.0
            if policy == "default_skippy":
                expected_note = "应 = 1.0，表示 capacity-aware 策略全部选中 server_1"
            elif policy == "fixed_node":
                expected_note = "应 = 0.0，表示 fixed_node 策略不会选中 server_1"
            else:
                expected_note = "按策略定义解释"
            rows.append({
                "metric": f"high_capacity_hit_ratio__{policy}",
                "value": float(ratio),
                "note": f"{policy} 策略选中 {capacity_target_node} 的比例（{expected_note}）",
            })

    # 2. per-workload policy 平均 probe duration（与 14 的 avg_probe_seconds 一致）
    if not summary_df.empty and "mean_probe_avg_duration" in summary_df.columns:
        for _, srow in summary_df.iterrows():
            policy = srow.get("policy")
            workload = srow.get("workload")
            duration = srow.get("mean_probe_avg_duration")
            if pd.notna(duration):
                rows.append({
                    "metric": f"{policy}__avg_probe_seconds__{workload}",
                    "value": float(duration),
                    "note": f"{policy} 策略在 {workload} 下的 mean_probe_avg_duration（sim 模型诚实特性：capacity 不改 single-invoke duration）",
                })

    # 3. per-workload speedup_ratio：fixed_node / default_skippy（>1 表示 baseline 更快）
    if not summary_df.empty and "mean_probe_avg_duration" in summary_df.columns:
        for workload, group in summary_df.groupby("workload"):
            d_row = group[group["policy"] == "default_skippy"]
            f_row = group[group["policy"] == "fixed_node"]
            if d_row.empty or f_row.empty:
                continue
            d_val = float(d_row["mean_probe_avg_duration"].iloc[0])
            f_val = float(f_row["mean_probe_avg_duration"].iloc[0])
            if d_val > 0:
                rows.append({
                    "metric": f"speedup_ratio_fixed_over_default_skippy__{workload}",
                    "value": float(f_val / d_val),
                    "note": f"在 {workload} 下，fixed_node / default_skippy 的 probe_avg_duration 比值（应 = 1.0，sim 诚实特性）",
                })

    # 4. per-workload relative change（来自 build_policy_comparison）
    if not comparison_df.empty and "mean_probe_avg_duration_relative" in comparison_df.columns:
        for _, crow in comparison_df.iterrows():
            workload = crow.get("workload")
            policy = crow.get("policy")
            rel = crow.get("mean_probe_avg_duration_relative")
            if pd.notna(rel):
                rows.append({
                    "metric": f"{policy}_vs_default_skippy__probe_avg_duration_relative__{workload}",
                    "value": float(rel),
                    "note": f"{policy} 相对 default_skippy baseline 的 probe_avg_duration 相对变化（应 = 0.0，sim 诚实特性）",
                })

    return pd.DataFrame(rows)
