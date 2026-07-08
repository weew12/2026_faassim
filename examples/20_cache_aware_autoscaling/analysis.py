"""
文件作用：cache_aware_autoscaling 样例的结果导出与分析工具。

该文件负责导出决策、控制计划、各类摘要、decision×plan 关联验证、
论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from models import AutoscalingDecision, ControlPlan

logger = logging.getLogger(__name__)


def decisions_to_dataframe(decisions: List[AutoscalingDecision]) -> pd.DataFrame:
    """
    将扩缩容决策转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in decisions])


def plans_to_dataframe(plans: List[ControlPlan]) -> pd.DataFrame:
    """
    将控制计划转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in plans])


def build_action_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成动作摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["action", "reason"])
        .agg(
            events=("function_name", "count"),
            avg_r_cache=("r_cache", "mean"),
            avg_r_load=("r_load", "mean"),
            avg_r_desired=("r_desired", "mean"),
            total_delta=("delta", "sum"),
        )
        .reset_index()
    )


def build_function_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    按函数生成摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby("function_name")
        .agg(
            records=("time", "count"),
            avg_cache_utility=("cache_utility", "mean"),
            max_r_cache=("r_cache", "max"),
            max_r_load=("r_load", "max"),
            max_r_desired=("r_desired", "max"),
            scale_out_events=("action", lambda s: int((s == "scale_out").sum())),
            scale_in_events=("action", lambda s: int((s == "scale_in").sum())),
            protect_events=("action", lambda s: int((s == "protect").sum())),
            prewarm_events=("action", lambda s: int((s == "prewarm").sum())),
        )
        .reset_index()
    )


def build_time_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    按时间生成总副本需求摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby("time")
        .agg(
            total_current_replicas=("current_replicas", "sum"),
            total_r_cache=("r_cache", "sum"),
            total_r_load=("r_load", "sum"),
            total_r_desired=("r_desired", "sum"),
            total_delta=("delta", "sum"),
            selected_cache_functions=("selected_by_cache_budget", "sum"),
        )
        .reset_index()
    )


def build_decision_plan_join(
    decision_df: pd.DataFrame,
    plan_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    decision × control_plan 关联（论文 demo 关键证据）。

    按 (time, function_name) 关联 decision 和 control_plan，验证：
    - 每个 decision 都对应一个 control_plan（行数一致）
    - decision.action 和 plan.control_action 一致
    - decision.r_desired == plan.target_replicas
    - scale_in 时若 in_flight > 0，则 safe_to_execute=False
    """
    if decision_df.empty or plan_df.empty:
        return pd.DataFrame()

    m = decision_df.merge(
        plan_df,
        on=["time", "function_name"],
        how="left",
        suffixes=("_decision", "_plan"),
    )

    rows: List[Dict[str, Any]] = []
    for _, r in m.iterrows():
        action = r.get("action")
        plan_action = r.get("control_action")
        target_r = r.get("target_replicas")
        desired = r.get("r_desired")
        in_flight = int(r.get("in_flight_requests", 0))
        safe = bool(r.get("safe_to_execute", False))
        executor = bool(r.get("executor_required", False))

        if pd.isna(plan_action):
            rows.append({
                "time": r["time"],
                "function_name": r["function_name"],
                "action": action,
                "plan_action": None,
                "target_replicas": None,
                "safe_to_execute": None,
                "match": False,
                "detail": "no matching plan",
            })
            continue

        decision_match = (action == plan_action)
        replicas_match = (int(target_r) == int(desired))
        safe_match = True
        detail = ""

        # scale_in 但有 in_flight → safe_to_execute 必须 False
        if action == "scale_in" and in_flight > 0 and safe:
            safe_match = False
            detail = "scale_in with in_flight>0 should not be safe_to_execute"

        # r_desired == current_replicas → executor_required=False
        if pd.notna(desired) and executor:
            if int(desired) == int(r.get("current_replicas", -1)):
                safe_match = False
                detail = "r_desired == current_replicas should not be executor_required"

        if not detail:
            detail = "ok" if (decision_match and replicas_match and safe_match) else "mismatch"

        rows.append({
            "time": r["time"],
            "function_name": r["function_name"],
            "action": action,
            "plan_action": plan_action,
            "target_replicas": int(target_r) if pd.notna(target_r) else None,
            "r_desired": int(desired) if pd.notna(desired) else None,
            "safe_to_execute": safe,
            "executor_required": executor,
            "in_flight_requests": in_flight,
            "match": bool(decision_match and replicas_match and safe_match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_paper_highlight(
    decision_df: pd.DataFrame,
    decision_plan_join_df: pd.DataFrame,
    config: Any,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要（含 note 列，沿用 02-19 模式）。

    cache_aware_autoscaling 样例的论文 demo 关注的是：
    1. R_cache vs R_load 主导关系：什么时候 R_load 主导（scale_out）vs R_cache 主导（prewarm）
    2. 容量预算利用：cache_budget 用了多少
    3. 决策分布：scale_out / scale_in / protect / prewarm / observe 各几个
    4. decision×plan 一致性
    """
    rows: List[Dict[str, Any]] = []

    if decision_df.empty:
        return pd.DataFrame(columns=["metric", "value", "note"])

    # 1. 决策分布
    for action in ["scale_out", "scale_in", "protect", "prewarm", "observe"]:
        n = int((decision_df["action"] == action).sum())
        rows.append({
            "metric": f"action_count__{action}",
            "value": n,
            "note": f"{action} 动作的 state 数（论文 demo 关键分布指标）",
        })

    # 2. R_cache vs R_load 主导分析
    if {"r_cache", "r_load"}.issubset(decision_df.columns):
        n_total = len(decision_df)
        n_load_dominant = int((decision_df["r_load"] > decision_df["r_cache"]).sum())
        n_cache_dominant = int(
            ((decision_df["r_cache"] > 0) & (decision_df["r_load"] == 0)).sum()
        )
        n_both = int(
            ((decision_df["r_cache"] > 0) & (decision_df["r_load"] > 0)).sum()
        )
        n_neither = int(
            ((decision_df["r_cache"] == 0) & (decision_df["r_load"] == 0)).sum()
        )
        rows.append({
            "metric": "r_load_dominant_events",
            "value": n_load_dominant,
            "note": "R_load > R_cache 主导的 events（R_load 触发扩容）",
        })
        rows.append({
            "metric": "r_cache_only_events",
            "value": n_cache_dominant,
            "note": "R_cache > 0 且 R_load == 0 的 events（仅靠 cache 保护）",
        })
        rows.append({
            "metric": "r_both_active_events",
            "value": n_both,
            "note": "R_cache > 0 且 R_load > 0 的 events（cache + load 同时保护）",
        })
        rows.append({
            "metric": "r_neither_active_events",
            "value": n_neither,
            "note": "R_cache == 0 且 R_load == 0 的 events（idle 状态）",
        })
        rows.append({
            "metric": "r_load_dominant_ratio",
            "value": float(n_load_dominant / n_total) if n_total > 0 else 0.0,
            "note": "R_load 主导占比（论文 demo 关键数字）",
        })

    # 3. 容量预算利用
    if "selected_by_cache_budget" in decision_df.columns:
        selected = decision_df[decision_df["selected_by_cache_budget"] == True]  # noqa: E712
        selected_mem_total = int(selected["memory_units"].sum())
        per_time_selected = (
            selected.groupby("time")["memory_units"].sum()
            if not selected.empty and "time" in selected.columns else pd.Series(dtype=float)
        )
        max_selected_mem_per_time = int(per_time_selected.max()) if not per_time_selected.empty else 0
        rows.append({
            "metric": "cache_budget_used",
            "value": selected_mem_total,
            "note": "被 cache budget 实际选中的 memory_units 跨 time 累加总和（不是单轮利用率）",
        })
        rows.append({
            "metric": "cache_budget_max_used_per_time",
            "value": max_selected_mem_per_time,
            "note": "单个 time 内被 cache budget 选中的最大 memory_units（用于计算利用率）",
        })
        rows.append({
            "metric": "cache_budget_total",
            "value": int(config.cache_capacity_budget_units),
            "note": "总 cache budget（= 5 unit）",
        })
        rows.append({
            "metric": "cache_budget_utilization",
            "value": float(max_selected_mem_per_time / config.cache_capacity_budget_units)
            if config.cache_capacity_budget_units > 0 else 0.0,
            "note": "单一 time 最大 cache budget 利用率（= max per-time selected memory / budget）",
        })
        # R_cache 被 budget 拒绝的次数
        rejected = int(
            ((decision_df["r_cache_raw"] > 0) & (decision_df["selected_by_cache_budget"] == False)).sum()  # noqa: E712
        )
        rows.append({
            "metric": "r_cache_rejected_by_budget",
            "value": rejected,
            "note": "R_cache > 0 但被 budget 拒绝的 events（被限缩为 0）",
        })

    # 4. decision×plan 一致性
    if not decision_plan_join_df.empty and "match" in decision_plan_join_df.columns:
        n = len(decision_plan_join_df)
        matched = int(decision_plan_join_df["match"].sum())
        rows.append({
            "metric": "decision_plan_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
            "note": "decision × control_plan join match 占比（论文 demo 关键证据，应 1.0）",
        })
        rows.append({
            "metric": "decision_plan_matched",
            "value": matched,
            "note": "matched 行数",
        })
        rows.append({
            "metric": "decision_plan_total",
            "value": n,
            "note": "decision×plan join 总行数（应 == decision 数）",
        })

    # 5. 时间序列上 R_cache vs R_load 总和
    if "time" in decision_df.columns:
        time_summary = (
            decision_df
            .groupby("time")
            .agg(
                total_r_cache=("r_cache", "sum"),
                total_r_load=("r_load", "sum"),
                total_r_desired=("r_desired", "sum"),
            )
            .reset_index()
        )
        for _, trow in time_summary.iterrows():
            t = float(trow["time"])
            rows.append({
                "metric": f"per_time_total_r_cache__{t}",
                "value": int(trow["total_r_cache"]),
                "note": f"time={t} 所有函数 R_cache 总和（per-time 时间序列）",
            })
            rows.append({
                "metric": f"per_time_total_r_load__{t}",
                "value": int(trow["total_r_load"]),
                "note": f"time={t} 所有函数 R_load 总和（per-time 时间序列）",
            })
            rows.append({
                "metric": f"per_time_total_r_desired__{t}",
                "value": int(trow["total_r_desired"]),
                "note": f"time={t} 所有函数 R_desired 总和（per-time 时间序列）",
            })

    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def self_check(
    decision_df: pd.DataFrame,
    plan_df: pd.DataFrame,
    decision_plan_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    config: Any,
) -> Dict[str, Any]:
    """
    数据自洽段（cache_aware_autoscaling 13 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    n_decisions = len(decision_df)
    n_plans = len(plan_df)

    # 1. decision 行数 == plan 行数（每个 decision 对应一个 plan）
    checks.append({
        "name": "decision_plan_count_match",
        "status": "PASS" if n_decisions == n_plans else "FAIL",
        "detail": f"decisions={n_decisions}, plans={n_plans}",
    })

    # 2. decision 行数 > 0
    checks.append({
        "name": "decision_count",
        "status": "PASS" if n_decisions > 0 else "FAIL",
        "detail": f"decisions={n_decisions}",
    })

    # 3. r_desired = max(r_cache, r_load) 在 clamp 后
    if "r_desired" in decision_df.columns and "r_cache" in decision_df.columns and "r_load" in decision_df.columns:
        actual = decision_df["r_desired"].tolist()
        expected = [
            max(int(r["r_cache"]), int(r["r_load"]))
            for _, r in decision_df.iterrows()
        ]
        all_match = all(int(a) == int(b) for a, b in zip(actual, expected))
        checks.append({
            "name": "r_desired_equals_max_r_cache_r_load",
            "status": "PASS" if all_match else "FAIL",
            "detail": f"all {n_decisions} decisions satisfy r_desired=max(r_cache, r_load)",
        })

    # 4. cache budget per time-point 不超（cache_budget 是每个时间点独立应用，不是跨时间点累加）
    if "selected_by_cache_budget" in decision_df.columns and "memory_units" in decision_df.columns and "time" in decision_df.columns:
        per_time_violation = 0
        max_mem_per_time = 0
        for t, group in decision_df.groupby("time"):
            selected_mem = int(
                group[group["selected_by_cache_budget"] == True]["memory_units"].sum()  # noqa: E712
            )
            max_mem_per_time = max(max_mem_per_time, selected_mem)
            if selected_mem > config.cache_capacity_budget_units:
                per_time_violation += 1
        checks.append({
            "name": "cache_budget_within_limit",
            "status": "PASS" if per_time_violation == 0 else "FAIL",
            "detail": f"per-time violations={per_time_violation}, "
                      f"max selected memory per time={max_mem_per_time}, budget={config.cache_capacity_budget_units}",
        })

    # 5. decision×plan join 100% match
    n_join = len(decision_plan_join_df)
    checks.append({
        "name": "decision_plan_join_row_count",
        "status": "PASS" if n_join == n_decisions else "FAIL",
        "detail": f"join rows={n_join}, decisions={n_decisions}",
    })
    if not decision_plan_join_df.empty and "match" in decision_plan_join_df.columns:
        n = len(decision_plan_join_df)
        matched = int(decision_plan_join_df["match"].sum())
        checks.append({
            "name": "decision_plan_join_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 6. action 字段只取 5 类有效值
    if "action" in decision_df.columns:
        actions = set(decision_df["action"].dropna().unique())
        expected = {"scale_out", "scale_in", "protect", "prewarm", "observe"}
        invalid = actions - expected
        checks.append({
            "name": "action_values_valid",
            "status": "PASS" if not invalid else "FAIL",
            "detail": f"observed={sorted(actions)}, invalid={sorted(invalid)}",
        })

    # 7. r_desired 在 [min_replicas, max_replicas] 范围内
    if "r_desired" in decision_df.columns:
        r_min = int(decision_df["r_desired"].min())
        r_max = int(decision_df["r_desired"].max())
        checks.append({
            "name": "r_desired_in_clamp_range",
            "status": "PASS" if r_min >= config.min_replicas and r_max <= config.max_replicas else "FAIL",
            "detail": f"r_desired range=[{r_min}, {r_max}], expected subset of [{config.min_replicas}, {config.max_replicas}]",
        })

    # 8. paper highlight 里 action_count 加总 == n_decisions
    if not paper_highlight_df.empty:
        action_counts = paper_highlight_df[
            paper_highlight_df.metric.str.startswith("action_count__")
        ]
        if not action_counts.empty:
            total = sum(int(v) for v in action_counts["value"])
            checks.append({
                "name": "paper_highlight_action_count_sum",
                "status": "PASS" if total == n_decisions else "FAIL",
                "detail": f"sum of action_count metrics={total}, decisions={n_decisions}",
            })

    # 9. paper highlight 里 decision_plan_consistency == 1.0
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "decision_plan_consistency"
        ]
        if not hl_rows.empty:
            v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_decision_plan_consistency",
                "status": "PASS" if v >= 0.999 else "FAIL",
                "detail": f"decision_plan_consistency={v:.4f}",
            })

    # 10. paper highlight 里的 cache_budget_utilization 应等于每个 time 最大选中 memory / budget
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "cache_budget_utilization"
        ]
        if not hl_rows.empty and "selected_by_cache_budget" in decision_df.columns:
            selected = decision_df[decision_df["selected_by_cache_budget"] == True]  # noqa: E712
            if selected.empty:
                expected_v = 0.0
            else:
                max_mem = float(selected.groupby("time")["memory_units"].sum().max())
                expected_v = max_mem / float(config.cache_capacity_budget_units)
            hl_v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_cache_budget_utilization",
                "status": "PASS" if abs(hl_v - expected_v) < 1e-6 else "FAIL",
                "detail": f"highlight={hl_v:.6f}, expected={expected_v:.6f}",
            })

    # 11. plan 安全语义：scale_in 且 in_flight>0 时不能 safe_to_execute
    if not decision_plan_join_df.empty:
        bad = decision_plan_join_df[
            (decision_plan_join_df["action"] == "scale_in")
            & (decision_plan_join_df["in_flight_requests"] > 0)
            & (decision_plan_join_df["safe_to_execute"] == True)  # noqa: E712
        ]
        checks.append({
            "name": "scale_in_in_flight_not_safe",
            "status": "PASS" if bad.empty else "FAIL",
            "detail": f"unsafe scale_in rows with in_flight>0: {len(bad)}",
        })

    # 12. 导出的表结构不应包含 pandas 默认索引列
    frames_to_check = {
        "decision": decision_df,
        "plan": plan_df,
        "decision_plan_join": decision_plan_join_df,
        "paper_highlight": paper_highlight_df,
    }
    bad_columns = []
    for name, df in frames_to_check.items():
        if df is None or df.empty:
            continue
        unnamed = [col for col in df.columns if str(col).startswith("Unnamed")]
        if unnamed:
            bad_columns.append(f"{name}:{','.join(unnamed)}")
    checks.append({
        "name": "export_tables_have_no_index_column",
        "status": "PASS" if not bad_columns else "FAIL",
        "detail": "no pandas index columns" if not bad_columns else "; ".join(bad_columns),
    })

    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {"checks": checks, "n_pass": n_pass, "n_fail": n_fail}


def log_self_check(self_check_result: Dict[str, Any]) -> None:
    """
    把数据自洽结果以表格形式 log。
    """
    checks = self_check_result.get("checks") or []
    if not checks:
        return

    logger.info("=== cache_aware_autoscaling self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(
    decisions: List[AutoscalingDecision],
    control_plans: List[ControlPlan],
    output_dir: Path,
    config: Any = None,
):
    """
    导出扩缩容决策结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_df = decisions_to_dataframe(decisions)
    plan_df = plans_to_dataframe(control_plans)

    action_summary_df = build_action_summary(decision_df)
    function_summary_df = build_function_summary(decision_df)
    time_summary_df = build_time_summary(decision_df)

    # decision×plan 关联（论文 demo 关键证据）
    decision_plan_join_df = build_decision_plan_join(decision_df, plan_df)
    join_path = output_dir / "cache_aware_autoscaling_decision_plan_join.csv"
    decision_plan_join_df.to_csv(join_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", join_path)

    # 论文 demo 关键摘要
    if config is None:
        from models import AutoscalingConfig
        config = AutoscalingConfig()
    paper_highlight_df = build_paper_highlight(decision_df, decision_plan_join_df, config)
    paper_highlight_path = output_dir / "cache_aware_autoscaling_paper_highlight.csv"
    paper_highlight_df.to_csv(paper_highlight_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", paper_highlight_path)

    # 数据自洽段
    self_check_result = self_check(
        decision_df, plan_df, decision_plan_join_df, paper_highlight_df, config,
    )
    log_self_check(self_check_result)

    # 导出 self_check 结果到 csv（沿用 02-19 模式）
    self_check_path = output_dir / "cache_aware_autoscaling_self_check.csv"
    self_check_df = pd.DataFrame(self_check_result.get("checks") or [])
    self_check_df.to_csv(self_check_path, index=False, encoding="utf-8-sig")
    logger.info("saved %s", self_check_path)

    outputs = {
        "cache_aware_autoscaling_decision": decision_df,
        "cache_aware_autoscaling_control_plan": plan_df,
        "cache_aware_autoscaling_action_summary": action_summary_df,
        "cache_aware_autoscaling_function_summary": function_summary_df,
        "cache_aware_autoscaling_time_summary": time_summary_df,
        "cache_aware_autoscaling_decision_plan_join": decision_plan_join_df,
        "cache_aware_autoscaling_paper_highlight": paper_highlight_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    outputs["cache_aware_autoscaling_self_check"] = self_check_df
    outputs["self_check_result"] = self_check_result
    return outputs
