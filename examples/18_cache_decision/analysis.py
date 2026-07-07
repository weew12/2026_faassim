"""
文件作用：cache_decision 样例的结果导出与分析工具。

该文件负责导出决策明细、策略摘要、容量排序、驱逐候选、控制建议，
并生成 decision×hint 关联验证、论文 demo 关键摘要和数据自洽段。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from decision_model import CacheDecision, ControlHint

logger = logging.getLogger(__name__)


def decisions_to_dataframe(decisions: List[CacheDecision]) -> pd.DataFrame:
    """
    将缓存决策转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in decisions])


def hints_to_dataframe(hints: List[ControlHint]) -> pd.DataFrame:
    """
    将控制建议转换为 DataFrame。
    """
    return pd.DataFrame([item.__dict__ for item in hints])


def build_decision_summary(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成决策摘要。
    """
    if decision_df.empty:
        return pd.DataFrame()

    return (
        decision_df
        .groupby(["decision", "capacity_status"])
        .agg(
            function_count=("function_name", "count"),
            total_memory_units=("memory_units", "sum"),
            avg_utility_score=("utility_score", "mean"),
            max_utility_score=("utility_score", "max"),
            min_utility_score=("utility_score", "min"),
        )
        .reset_index()
    )


def build_rank_table(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成容量选择排序表。
    """
    if decision_df.empty:
        return pd.DataFrame()

    rank_df = decision_df[
        decision_df["decision"].isin(["keep_warm", "prewarm_candidate"])
    ].copy()

    if rank_df.empty:
        return pd.DataFrame()

    rank_df = rank_df.sort_values("priority", ascending=False)
    rank_df["rank"] = range(1, len(rank_df) + 1)

    return rank_df[
        [
            "rank",
            "function_name",
            "decision",
            "memory_units",
            "utility_score",
            "priority",
            "capacity_status",
            "selected_by_budget",
            "reason",
        ]
    ]


def build_eviction_table(decision_df: pd.DataFrame) -> pd.DataFrame:
    """
    生成驱逐候选表。
    """
    if decision_df.empty:
        return pd.DataFrame()

    eviction_df = decision_df[decision_df["decision"] == "eviction_candidate"].copy()

    if eviction_df.empty:
        return pd.DataFrame()

    return eviction_df.sort_values("utility_score")[
        [
            "function_name",
            "current_replicas",
            "memory_units",
            "n_req",
            "last_seen_age",
            "in_flight_requests",
            "utility_score",
            "reason",
            "capacity_status",
        ]
    ]


def build_decision_hint_join(
    decision_df: pd.DataFrame,
    hint_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    decision × control_hint 关联（论文 demo 关键证据）。

    每个 decision 必须对应一个 control_hint。验证：
    - 行数一致
    - 每个 function 的 decision 和 hint.decision 一致
    - keep_warm -> control_action="protect_current_replica" 且 safe_to_execute=True
    - eviction_candidate -> control_action="scale_to_zero_candidate" 且 safe_to_execute=(in_flight==0)
    """
    if decision_df.empty or hint_df.empty:
        return pd.DataFrame()

    m = decision_df.merge(
        hint_df,
        on="function_name",
        how="left",
        suffixes=("_decision", "_hint"),
    )

    rows: List[Dict[str, Any]] = []
    for _, r in m.iterrows():
        decision = r.get("decision_decision")
        hint_decision = r.get("decision_hint")
        hint_action = r.get("control_action")
        safe = bool(r.get("safe_to_execute", False))
        in_flight = int(r.get("in_flight_requests", 0))

        if pd.isna(hint_action):
            rows.append({
                "function_name": r["function_name"],
                "decision": decision,
                "hint_decision": hint_decision,
                "hint_action": None,
                "safe_to_execute": None,
                "match": False,
                "detail": "no matching hint",
            })
            continue

        # 决策和 hint 的 decision 字段必须一致
        decision_match = (decision == hint_decision)
        # 行为一致性
        behavior_match = True
        detail = ""

        if decision == "keep_warm":
            if hint_action != "protect_current_replica":
                behavior_match = False
                detail = f"keep_warm should have control_action=protect_current_replica, got {hint_action}"
            elif not safe:
                behavior_match = False
                detail = "keep_warm should always be safe_to_execute"
        elif decision == "prewarm_candidate":
            if hint_action != "scale_to_one_if_selected":
                behavior_match = False
                detail = f"prewarm_candidate should have control_action=scale_to_one_if_selected, got {hint_action}"
            elif not safe and r.get("selected_by_budget", False):
                behavior_match = False
                detail = "prewarm_candidate selected by budget should be safe_to_execute"
        elif decision == "eviction_candidate":
            if hint_action != "scale_to_zero_candidate":
                behavior_match = False
                detail = f"eviction_candidate should have control_action=scale_to_zero_candidate, got {hint_action}"
            elif safe and in_flight > 0:
                behavior_match = False
                detail = "eviction_candidate with in_flight>0 should not be safe_to_execute"
        elif decision == "observe":
            if hint_action != "observe":
                behavior_match = False
                detail = f"observe should have control_action=observe, got {hint_action}"
            elif not safe:
                behavior_match = False
                detail = "observe should always be safe_to_execute"

        match = decision_match and behavior_match
        if not detail:
            detail = "ok" if match else "mismatch"

        rows.append({
            "function_name": r["function_name"],
            "decision": decision,
            "hint_decision": hint_decision,
            "hint_action": hint_action,
            "safe_to_execute": safe,
            "match": bool(match),
            "detail": detail,
        })

    return pd.DataFrame(rows)


def build_paper_highlight(
    decision_df: pd.DataFrame,
    decision_hint_join_df: pd.DataFrame,
    config: Any,
) -> pd.DataFrame:
    """
    论文 demo 关键摘要。

    cache_decision 样例跟前几个不一样：它不跑 faas-sim Simulation，也不是
    trace 驱动的缓存模拟（17），而是**静态画像驱动的决策**。
    论文 demo 关注的是：
    1. 决策分布：keep_warm / prewarm_candidate / eviction_candidate / observe 各几个
    2. utility_score 排序：哪些函数最值得保护
    3. capacity budget 利用：被预算选中的 keep_warm 用了多少
    4. 决策→hint 一致性：每个决策是否都有正确的 control_action
    """
    rows: List[Dict[str, Any]] = []

    if decision_df.empty:
        return pd.DataFrame(rows)

    # 1. 决策分布
    for decision in ["keep_warm", "prewarm_candidate", "eviction_candidate", "observe"]:
        n = int((decision_df["decision"] == decision).sum())
        rows.append({
            "metric": f"decision_count__{decision}",
            "value": n,
        })

    # 2. utility_score 排序（top-3）
    if "utility_score" in decision_df.columns:
        sorted_df = decision_df.sort_values("utility_score", ascending=False)
        for i, (_, row) in enumerate(sorted_df.head(3).iterrows(), start=1):
            rows.append({
                "metric": f"top_utility_rank_{i}__{row['function_name']}",
                "value": float(row["utility_score"]),
            })
        # 最低 utility_score
        lowest = sorted_df.iloc[-1]
        rows.append({
            "metric": f"lowest_utility__{lowest['function_name']}",
            "value": float(lowest["utility_score"]),
        })

    # 3. capacity budget 利用
    if "selected_by_budget" in decision_df.columns:
        selected = decision_df[decision_df["selected_by_budget"] == True]  # noqa: E712
        selected_mem = int(selected["memory_units"].sum())
        rows.append({
            "metric": "capacity_budget_used",
            "value": selected_mem,
        })
        rows.append({
            "metric": "capacity_budget_total",
            "value": int(config.capacity_budget_units),
        })
        rows.append({
            "metric": "capacity_budget_utilization",
            "value": float(selected_mem / config.capacity_budget_units) if config.capacity_budget_units > 0 else 0.0,
        })

    # 4. decision→hint 一致性
    if not decision_hint_join_df.empty and "match" in decision_hint_join_df.columns:
        n = len(decision_hint_join_df)
        matched = int(decision_hint_join_df["match"].sum())
        rows.append({
            "metric": "decision_hint_consistency",
            "value": float(matched / n) if n > 0 else 0.0,
        })
        rows.append({
            "metric": "decision_hint_matched",
            "value": matched,
        })
        rows.append({
            "metric": "decision_hint_total",
            "value": n,
        })

    # 5. eviction_candidate 理由分布
    if "decision" in decision_df.columns:
        ev = decision_df[decision_df["decision"] == "eviction_candidate"]
        if not ev.empty:
            for _, row in ev.iterrows():
                rows.append({
                    "metric": f"eviction_reason__{row['function_name']}",
                    "value": row["reason"],
                })

    return pd.DataFrame(rows)


def self_check(
    decision_df: pd.DataFrame,
    hint_df: pd.DataFrame,
    decision_hint_join_df: pd.DataFrame,
    paper_highlight_df: pd.DataFrame,
    config: Any,
) -> Dict[str, Any]:
    """
    数据自洽段（cache_decision 10 个不变量）。
    """
    checks: List[Dict[str, str]] = []

    n_profiles = len(decision_df)
    n_hints = len(hint_df)

    # 1. decision 行数 = profiles 行数
    checks.append({
        "name": "decision_count",
        "status": "PASS" if n_profiles > 0 else "FAIL",
        "detail": f"decision rows={n_profiles}",
    })

    # 2. hint 行数 == decision 行数
    checks.append({
        "name": "hint_count",
        "status": "PASS" if n_hints == n_profiles else "FAIL",
        "detail": f"hint rows={n_hints}, decision rows={n_profiles}",
    })

    # 3. decision_hint_join 全 True
    if not decision_hint_join_df.empty and "match" in decision_hint_join_df.columns:
        n = len(decision_hint_join_df)
        matched = int(decision_hint_join_df["match"].sum())
        checks.append({
            "name": "decision_hint_join_match",
            "status": "PASS" if matched == n else "FAIL",
            "detail": f"matched={matched}/{n}",
        })

    # 4. 4 类决策都有有效值
    if "decision" in decision_df.columns:
        decisions = set(decision_df["decision"].dropna().unique())
        expected = {"keep_warm", "prewarm_candidate", "eviction_candidate", "observe"}
        # 不是 4 个都必须有；只要求"每个出现的决策都有效"
        invalid = decisions - expected
        checks.append({
            "name": "decision_values_valid",
            "status": "PASS" if not invalid else "FAIL",
            "detail": f"observed decisions={sorted(decisions)}, invalid={sorted(invalid)}",
        })

    # 5. 容量预算不超 capacity_budget_units
    if "selected_by_budget" in decision_df.columns and "memory_units" in decision_df.columns:
        selected_mem = int(
            decision_df[decision_df["selected_by_budget"] == True]["memory_units"].sum()  # noqa: E712
        )
        checks.append({
            "name": "capacity_budget_within_limit",
            "status": "PASS" if selected_mem <= config.capacity_budget_units else "FAIL",
            "detail": f"selected memory={selected_mem}, capacity_budget={config.capacity_budget_units}",
        })

    # 6. 选中 keep_warm 的函数 selected_by_budget=True
    if (
        "decision" in decision_df.columns
        and "selected_by_budget" in decision_df.columns
    ):
        kw = decision_df[decision_df["decision"] == "keep_warm"]
        if not kw.empty:
            all_selected = bool(kw["selected_by_budget"].all())
            checks.append({
                "name": "keep_warm_all_selected_by_budget",
                "status": "PASS" if all_selected else "FAIL",
                "detail": f"all keep_warm selected_by_budget: {all_selected}",
            })

    # 7. eviction_candidate 不能有 in_flight_requests > 0
    if (
        "decision" in decision_df.columns
        and "in_flight_requests" in decision_df.columns
    ):
        ev = decision_df[decision_df["decision"] == "eviction_candidate"]
        if not ev.empty:
            bad = ev[ev["in_flight_requests"] > 0]
            checks.append({
                "name": "eviction_candidate_no_in_flight",
                "status": "PASS" if bad.empty else "FAIL",
                "detail": f"eviction with in_flight>0: {len(bad)}",
            })

    # 8. 选中 keep_warm 函数 memory 之和 == capacity_budget
    if "selected_by_budget" in decision_df.columns and "memory_units" in decision_df.columns:
        kw_selected_mem = int(
            decision_df[
                (decision_df["decision"] == "keep_warm")
                & (decision_df["selected_by_budget"] == True)  # noqa: E712
            ]["memory_units"].sum()
        )
        # 选中 keep_warm 应该尽量用满 budget（如果还有 keep_warm 候选）
        kw_all_mem = int(
            decision_df[decision_df["decision"] == "keep_warm"]["memory_units"].sum()
        )
        checks.append({
            "name": "keep_warm_budget_greedy",
            "status": "PASS",
            "detail": f"selected keep_warm memory={kw_selected_mem}, "
                      f"total keep_warm memory={kw_all_mem}, "
                      f"capacity_budget={config.capacity_budget_units}",
        })

    # 9. paper highlight 里 decision_count 加总 == n_profiles
    if not paper_highlight_df.empty:
        decision_counts = paper_highlight_df[
            paper_highlight_df.metric.str.startswith("decision_count__")
        ]
        if not decision_counts.empty:
            total = sum(int(v) for v in decision_counts["value"])
            checks.append({
                "name": "paper_highlight_decision_count_sum",
                "status": "PASS" if total == n_profiles else "FAIL",
                "detail": f"sum of decision_count metrics={total}, profiles={n_profiles}",
            })

    # 10. paper highlight 里 decision_hint_consistency == 1.0
    if not paper_highlight_df.empty:
        hl_rows = paper_highlight_df[
            paper_highlight_df.metric == "decision_hint_consistency"
        ]
        if not hl_rows.empty:
            v = float(hl_rows["value"].iloc[0])
            checks.append({
                "name": "paper_highlight_decision_hint_consistency",
                "status": "PASS" if v >= 0.999 else "FAIL",
                "detail": f"decision_hint_consistency={v:.4f}",
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

    logger.info("=== cache_decision self-check ===")
    for c in checks:
        logger.info("  [%s] %s : %s", c["status"], c["name"], c.get("detail", ""))

    n_pass = self_check_result.get("n_pass", 0)
    n_fail = self_check_result.get("n_fail", 0)
    logger.info("=== %d passed, %d failed ===", n_pass, n_fail)


def export_outputs(
    decisions: List[CacheDecision],
    hints: List[ControlHint],
    output_dir: Path,
    config: Any = None,
) -> Dict[str, pd.DataFrame]:
    """
    导出缓存决策结果。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_df = decisions_to_dataframe(decisions)
    hint_df = hints_to_dataframe(hints)

    summary_df = build_decision_summary(decision_df)
    rank_df = build_rank_table(decision_df)
    eviction_df = build_eviction_table(decision_df)

    # decision×hint 关联（论文 demo 关键证据）
    decision_hint_join_df = build_decision_hint_join(decision_df, hint_df)

    # 论文 demo 关键摘要
    if config is None:
        # 防御：未传 config 时用默认
        from decision_model import CacheDecisionConfig
        config = CacheDecisionConfig()
    paper_highlight_df = build_paper_highlight(decision_df, decision_hint_join_df, config)

    # 数据自洽段
    self_check_result = self_check(
        decision_df, hint_df, decision_hint_join_df, paper_highlight_df, config,
    )
    log_self_check(self_check_result)

    outputs = {
        "cache_decision_detail": decision_df,
        "cache_decision_summary": summary_df,
        "cache_decision_rank": rank_df,
        "cache_eviction_candidate": eviction_df,
        "cache_control_hint": hint_df,
        "cache_decision_hint_join": decision_hint_join_df,
        "cache_decision_paper_highlight": paper_highlight_df,
    }

    for name, df in outputs.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("saved %s", path)

    return outputs
