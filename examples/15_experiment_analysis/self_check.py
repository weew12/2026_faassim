"""
文件作用：批量结果自洽检查。

保证 experiment_analysis 输出的 CSV 之间能相互印证，
跟 14_batch_experiment 的 self_check_batch_results 风格一致。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


def self_check(
    run_metrics_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    output_dir=None,
) -> Dict[str, Any]:
    """
    数据自洽段。

    校验：
    1. run_metrics 行数 >= 2（至少 2 个 case）
    2. probe_events 总数 = invocation_events 总数
    3. 每个 run 的 probe_events = invocation_events
    4. summary 行数 = policy × workload 笛卡尔积
    5. comparison 行数 = (policy-1) × workload（baseline 自身被跳过）
    6. paper highlight 里 high_capacity_hit_ratio 与 run_metrics 一致且符合 14 的策略设计
    7. summary 跟 paper highlight 里 avg_probe_seconds__<workload> 一致

    返回 dict 包含：
    - checks：list[dict]（name/status/detail）
    - n_pass / n_fail：统计
    - output_path：self_check.csv 路径（如果传了 output_dir）
    """
    checks: List[Dict[str, str]] = []

    n_runs = len(run_metrics_df)
    checks.append({
        "name": "run_metrics_min_rows",
        "status": "PASS" if n_runs >= 2 else "FAIL",
        "detail": f"run_metrics rows={n_runs}",
    })

    if {"probe_events", "invocation_events"}.issubset(run_metrics_df.columns):
        total_probes = int(run_metrics_df["probe_events"].sum())
        total_invocations = int(run_metrics_df["invocation_events"].sum())
        checks.append({
            "name": "total_probe_equals_total_invocation",
            "status": "PASS" if total_probes == total_invocations else "FAIL",
            "detail": f"total_probes={total_probes}, total_invocations={total_invocations}",
        })

        per_run_match = bool((run_metrics_df["probe_events"] == run_metrics_df["invocation_events"]).all())
        mismatch_count = int((run_metrics_df["probe_events"] != run_metrics_df["invocation_events"]).sum())
        checks.append({
            "name": "per_run_probe_equals_invocation",
            "status": "PASS" if per_run_match else "FAIL",
            "detail": f"mismatch_runs={mismatch_count}/{len(run_metrics_df)}",
        })

    # summary 行列数自洽
    if not summary_df.empty and {"policy", "workload"}.issubset(summary_df.columns):
        n_policies = run_metrics_df["policy"].nunique() if "policy" in run_metrics_df.columns else 0
        n_workloads = run_metrics_df["workload"].nunique() if "workload" in run_metrics_df.columns else 0
        expected_summary = n_policies * n_workloads
        actual_summary = len(summary_df)
        checks.append({
            "name": "summary_row_count",
            "status": "PASS" if actual_summary == expected_summary else "FAIL",
            "detail": f"summary rows={actual_summary}, expected={expected_summary} (policies={n_policies} × workloads={n_workloads})",
        })

    # comparison 行列数 = (policies-1) × workloads（baseline 自身被跳过）
    if not comparison_df.empty and {"policy", "workload"}.issubset(comparison_df.columns):
        n_policies = run_metrics_df["policy"].nunique() if "policy" in run_metrics_df.columns else 0
        n_workloads = run_metrics_df["workload"].nunique() if "workload" in run_metrics_df.columns else 0
        expected_comp = (n_policies - 1) * n_workloads if n_policies >= 2 else 0
        actual_comp = len(comparison_df)
        checks.append({
            "name": "comparison_row_count",
            "status": "PASS" if actual_comp == expected_comp else "FAIL",
            "detail": f"comparison rows={actual_comp}, expected={expected_comp} ((policies-1={n_policies-1}) × workloads={n_workloads})",
        })
    elif comparison_df.empty and n_runs >= 2:
        # 当所有 policy 只有一个（== baseline）时 comparison 允许为空
        n_policies = run_metrics_df["policy"].nunique() if "policy" in run_metrics_df.columns else 0
        if n_policies >= 2:
            checks.append({
                "name": "comparison_row_count",
                "status": "FAIL",
                "detail": "comparison empty but >= 2 policies in run_metrics",
            })

    # paper highlight 命中率 vs run_metrics
    expected_high_capacity_ratio = {
        "default_skippy": 1.0,
        "fixed_node": 0.0,
    }
    if not paper_highlight_df.empty and "scheduled_node" in run_metrics_df.columns:
        for policy in run_metrics_df["policy"].dropna().unique():
            sub = run_metrics_df[run_metrics_df.policy == policy]
            total = len(sub)
            high = int((sub["scheduled_node"] == "server_1").sum())
            ratio = (high / total) if total > 0 else 0.0
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"high_capacity_hit_ratio__{policy}"
            ]
            if hl_rows.empty:
                checks.append({
                    "name": f"high_capacity_hit_ratio__{policy}",
                    "status": "FAIL",
                    "detail": f"paper highlight missing for {policy}",
                })
                continue
            hl_value = float(hl_rows["value"].iloc[0])
            expected_ratio = expected_high_capacity_ratio.get(policy)
            expected_ok = True if expected_ratio is None else abs(ratio - expected_ratio) < 1e-9
            match = abs(hl_value - ratio) < 1e-6 and expected_ok
            expected_text = "not fixed" if expected_ratio is None else f"{expected_ratio:.2f}"
            checks.append({
                "name": f"high_capacity_hit_ratio__{policy}",
                "status": "PASS" if match else "FAIL",
                "detail": f"hit {high}/{total} = {ratio:.2f}, highlight={hl_value:.2f}, expected={expected_text}",
            })

    # summary 跟 paper highlight 里 avg_probe_seconds 一致
    if (
        not summary_df.empty
        and not paper_highlight_df.empty
        and "mean_probe_avg_duration" in summary_df.columns
    ):
        for _, srow in summary_df.iterrows():
            policy = srow["policy"]
            workload = srow["workload"]
            v_summary = float(srow["mean_probe_avg_duration"])
            hl_rows = paper_highlight_df[
                paper_highlight_df.metric == f"{policy}__avg_probe_seconds__{workload}"
            ]
            if hl_rows.empty:
                continue
            v_hl = float(hl_rows["value"].iloc[0])
            match = abs(v_hl - v_summary) < 1e-6
            checks.append({
                "name": f"avg_probe_seconds_consistency__{policy}__{workload}",
                "status": "PASS" if match else "FAIL",
                "detail": f"summary={v_summary:.6f}, highlight={v_hl:.6f}",
            })

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")

    # 写到 self_check.csv（仿 14 batch_self_check.csv）
    output_path = None
    if output_dir is not None:
        check_df = pd.DataFrame(checks)
        if "status" in check_df.columns:
            check_df["passed"] = check_df["status"] == "PASS"
        output_path = Path(output_dir) / "self_check.csv"
        check_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", output_path)

    return {
        "checks": checks,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "output_path": output_path,
    }


def log_self_check(self_check_result: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log（与 14_batch_experiment 风格一致）。
    """
    checks = self_check_result.get("checks") or []
    if not checks:
        return

    logger.info("=== experiment_analysis self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)
